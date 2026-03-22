"""Astar Island prediction pipeline.

Orchestrates the prediction workflow: initialize model from round data,
run viewport queries, fit predictor parameters, and submit predictions.
All received data is saved to submissions/<round_number>/.

Usage:
    uv run python -m astar_island.predict --round-id ROUND_ID
"""

import argparse
import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

from astar_island.client import AstarIslandClient
from astar_island.client import ViewPortData
from astar_island.model import IslandModel
from astar_island.model import IslandPredictor
from astar_island.query_selector import select_queries
from astar_island.visualize import plot_heatmap_combined
from astar_island.visualize import plot_heatmap_grid

LOGGER = logging.getLogger(__name__)

SUBMISSIONS_DIR = Path(__file__).parent / "submissions"


def _save_viewports(submission_dir: Path, viewports: list[ViewPortData]) -> None:
    """Save viewport data immediately after querying."""
    submission_dir.mkdir(parents=True, exist_ok=True)

    viewport_records = [
        {
            "round_id": vp.round_id,
            "seed_index": vp.seed_index,
            "viewport_x": vp.viewport_x,
            "viewport_y": vp.viewport_y,
            "viewport_w": vp.viewport_w,
            "viewport_h": vp.viewport_h,
            "grid": vp.grid.tolist(),
        }
        for vp in viewports
    ]
    (submission_dir / "viewports.json").write_text(json.dumps(viewport_records, indent=2))
    LOGGER.info("Saved %d viewports to %s", len(viewports), submission_dir)


def _save_predictions(
    submission_dir: Path,
    round_number: int,
    predictions: dict[int, NDArray[np.float64]],
    rules_summary: str,
) -> None:
    """Save predictions, plots, and metadata."""
    submission_dir.mkdir(parents=True, exist_ok=True)

    pred_arrays = {f"seed_{k}": v for k, v in predictions.items()}
    np.savez_compressed(submission_dir / "predictions.npz", **pred_arrays)  # type: ignore[arg-type]

    # Save per-seed prediction heatmaps
    for seed_idx, preds in predictions.items():
        seed_dir = submission_dir / f"seed_{seed_idx}"
        seed_dir.mkdir(parents=True, exist_ok=True)

        fig = plot_heatmap_grid(preds, suptitle=f"Seed {seed_idx} — Predictions")
        fig.savefig(
            seed_dir / "pred_channels.png",
            dpi=150,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )
        plt.close(fig)

        fig = plot_heatmap_combined(preds, title=f"Seed {seed_idx} — Predictions Combined")
        fig.savefig(
            seed_dir / "pred_combined.png",
            dpi=150,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )
        plt.close(fig)

    meta = {
        "round_number": round_number,
        "n_seeds": len(predictions),
        "rules": rules_summary,
    }
    (submission_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
    LOGGER.info("Saved predictions and plots to %s", submission_dir)


def _load_viewports(submission_dir: Path) -> list[ViewPortData]:
    """Load saved viewports from a submission directory."""
    vp_path = submission_dir / "viewports.json"
    records = json.loads(vp_path.read_text())
    return [
        ViewPortData(
            round_id=r["round_id"],
            seed_index=r["seed_index"],
            viewport_x=r["viewport_x"],
            viewport_y=r["viewport_y"],
            viewport_w=r["viewport_w"],
            viewport_h=r["viewport_h"],
            grid=np.array(r["grid"], dtype=np.int16),
        )
        for r in records
    ]


def run_prediction_pipeline(
    client: AstarIslandClient,
    round_id: str,
    predictor: IslandPredictor,
) -> dict[int, NDArray[np.float64]]:
    """Full prediction pipeline for a round.

    1. Fetch round data and budget
    2. Initialize model with predictor
    3. Run 50 strategic viewport queries
    4. Fit predictor parameters on observations
    5. Save all data and submit predictions

    Args:
        client: API client.
        round_id: Round UUID.
        predictor: Predictor to use for predictions.

    Returns:
        Dict mapping seed_index to (H, W, 6) prediction arrays.
    """
    round_data = client.get_round(round_id)
    budget_data = client.get_budget()

    LOGGER.info(
        "Round %d (%s): %dx%d map, %d seeds, status=%s, budget=%d/%d",
        round_data.round_number,
        round_data.id[:8],
        round_data.map_height,
        round_data.map_width,
        round_data.seeds_count,
        round_data.status,
        budget_data.queries_used,
        budget_data.queries_max,
    )

    # Initialize model
    model = IslandModel.from_round_data(round_data=round_data, predictor=predictor)
    LOGGER.info("Model initialized with %d seeds", round_data.seeds_count)

    # Run viewport queries (50 strategic queries)
    submission_dir = SUBMISSIONS_DIR / f"round_{round_data.round_number:02d}"
    queries = select_queries(model)
    for i, (seed_idx, x, y) in enumerate(queries):
        LOGGER.info("Query %d/%d: seed=%d, x=%d, y=%d", i + 1, len(queries), seed_idx, x, y)
        result = client.simulate(round_id, seed_idx, x, y)
        model.update(result)
    LOGGER.info("Ran %d viewport queries", len(queries))

    # Save viewports immediately (before fitting, in case something fails)
    _save_viewports(submission_dir, model.observed_viewports)

    # Generate predictions, save, and submit
    return _predict_and_submit(client, round_id, model, submission_dir)


def resubmit_pipeline(
    client: AstarIslandClient,
    round_id: str,
    round_number: int,
    predictor: IslandPredictor,
) -> dict[int, NDArray[np.float64]]:
    """Resubmit predictions from saved viewports (no new queries).

    Loads viewports from submissions/<round_number>/, re-fits the predictor,
    and resubmits predictions.

    Args:
        client: API client.
        round_id: Round UUID.
        round_number: Round number (to find saved viewports).
        predictor: Predictor to use for predictions.

    Returns:
        Dict mapping seed_index to (H, W, 6) prediction arrays.
    """
    round_data = client.get_round(round_id)

    # Initialize model
    model = IslandModel.from_round_data(round_data=round_data, predictor=predictor)

    # Load saved viewports
    submission_dir = SUBMISSIONS_DIR / f"round_{round_number:02d}"
    viewports = _load_viewports(submission_dir)
    LOGGER.info("Loaded %d viewports from %s", len(viewports), submission_dir)

    for vp in viewports:
        model.update(vp)

    # Generate predictions, save, and submit
    return _predict_and_submit(client, round_id, model, submission_dir)


def _predict_and_submit(
    client: AstarIslandClient,
    round_id: str,
    model: IslandModel,
    submission_dir: Path,
) -> dict[int, NDArray[np.float64]]:
    """Generate predictions, save artifacts, and submit."""
    n_seeds = len(model.initial_states)

    # Generate predictions (auto-fits predictor on first call)
    predictions: dict[int, NDArray[np.float64]] = {}
    for seed_idx in range(n_seeds):
        predictions[seed_idx] = model.predict(seed_idx)

    LOGGER.info("Rules: %s", model.rules.summary())

    # Save predictions and metadata
    _save_predictions(submission_dir, 0, predictions, model.rules.summary())

    # Submit predictions
    for seed_idx, preds in predictions.items():
        result = client.submit(round_id=round_id, seed_index=seed_idx, prediction=preds)
        LOGGER.info("Seed %d submission: %s", seed_idx, result)

    return predictions


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Astar Island prediction pipeline")
    parser.add_argument("--round-id", required=True, help="Round ID (UUID string)")
    parser.add_argument(
        "--resubmit",
        type=int,
        default=None,
        metavar="ROUND_NUM",
        help="Resubmit from saved viewports for this round number (no new queries)",
    )
    args = parser.parse_args()

    from astar_island.config import get_access_token  # noqa: PLC0415
    from astar_island.predictor import DiffusionPredictor  # noqa: PLC0415

    client = AstarIslandClient(token=get_access_token())
    predictor = DiffusionPredictor()

    if args.resubmit is not None:
        resubmit_pipeline(client, args.round_id, args.resubmit, predictor)
    else:
        run_prediction_pipeline(client, args.round_id, predictor=predictor)


if __name__ == "__main__":
    main()
