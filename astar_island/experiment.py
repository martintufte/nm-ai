"""Offline experiment runner for Astar Island predictors.

Runs a predictor against a saved round using the simulator, optionally
performing viewport queries, then saves scores and heatmap artifacts.

Usage:
    uv run python -m astar_island.experiment --round 1 --predictor diffusion
    uv run python -m astar_island.experiment --round 1 --predictor diffusion --queries 50
"""

import argparse
import json
import logging
from datetime import UTC
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

from astar_island.model import IslandModel
from astar_island.model import IslandPredictor
from astar_island.simulator import VIEWPORT_SIZE
from astar_island.simulator import AstarIslandSimulator
from astar_island.visualize import plot_heatmap_combined
from astar_island.visualize import plot_heatmap_grid

LOGGER = logging.getLogger(__name__)

EXPERIMENTS_DIR = Path(__file__).parent / "experiments"
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def _create_experiment_dir(name: str) -> Path:
    """Create a timestamped experiment directory."""
    timestamp = datetime.now(UTC).strftime(TIMESTAMP_FORMAT)
    exp_dir = EXPERIMENTS_DIR / f"{timestamp}_{name}"
    exp_dir.mkdir(parents=True, exist_ok=True)
    return exp_dir


def _distribute_queries(n_queries: int, n_seeds: int) -> list[int]:
    """Distribute queries evenly across seeds."""
    base = n_queries // n_seeds
    remainder = n_queries % n_seeds
    return [base + (1 if i < remainder else 0) for i in range(n_seeds)]


def _pick_viewport_positions(
    h: int,
    w: int,
    n_queries: int,
    rng: np.random.Generator,
) -> list[tuple[int, int]]:
    """Pick random viewport top-left positions within map bounds."""
    max_x = max(0, w - VIEWPORT_SIZE)
    max_y = max(0, h - VIEWPORT_SIZE)
    xs = rng.integers(0, max_x + 1, size=n_queries)
    ys = rng.integers(0, max_y + 1, size=n_queries)
    return list(zip(xs.tolist(), ys.tolist(), strict=True))


def _save_heatmaps(
    exp_dir: Path,
    seed_idx: int,
    ground_truth: NDArray[np.float64],
    predictions: NDArray[np.float64],
) -> None:
    """Save ground truth and prediction heatmaps for a single seed."""
    seed_dir = exp_dir / f"seed_{seed_idx}"
    seed_dir.mkdir(parents=True, exist_ok=True)

    # Ground truth channel heatmaps
    fig = plot_heatmap_grid(ground_truth, suptitle=f"Seed {seed_idx} — Ground Truth")
    fig.savefig(
        seed_dir / "gt_channels.png",
        dpi=150,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)

    # Ground truth combined
    fig = plot_heatmap_combined(ground_truth, title=f"Seed {seed_idx} — Ground Truth Combined")
    fig.savefig(
        seed_dir / "gt_combined.png",
        dpi=150,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)

    # Prediction channel heatmaps
    fig = plot_heatmap_grid(predictions, suptitle=f"Seed {seed_idx} — Predictions")
    fig.savefig(
        seed_dir / "pred_channels.png",
        dpi=150,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)

    # Prediction combined
    fig = plot_heatmap_combined(predictions, title=f"Seed {seed_idx} — Predictions Combined")
    fig.savefig(
        seed_dir / "pred_combined.png",
        dpi=150,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)


def _save_score_summary(
    exp_dir: Path,
    scores: dict[int, float],
    avg_score: float,
) -> None:
    """Save a bar chart of per-seed scores."""
    seeds = sorted(scores.keys())
    values = [scores[s] for s in seeds]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar([f"Seed {s}" for s in seeds], values, color="#30b5c7")
    ax.axhline(
        avg_score,
        color="#f08c00",
        linestyle="--",
        linewidth=2,
        label=f"Avg: {avg_score:.1f}",
    )
    ax.set_ylabel("Score")
    ax.set_title("Entropy-Weighted KL Score per Seed")
    ax.set_ylim(0, 100)
    ax.legend()

    for bar, val in zip(bars, values, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1,
            f"{val:.1f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )

    fig.tight_layout()
    fig.savefig(exp_dir / "scores.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def run_experiment(
    round_number: int,
    predictor: IslandPredictor,
    predictor_name: str,
    n_queries: int = 0,
    rng_seed: int = 42,
) -> Path:
    """Run a full offline experiment.

    Args:
        round_number: Which saved round to use.
        predictor: The predictor to benchmark.
        predictor_name: Name for the experiment directory.
        n_queries: Number of viewport queries to run (0 = no queries).
        rng_seed: Random seed for reproducibility.

    Returns:
        Path to the experiment directory.
    """
    rng = np.random.default_rng(rng_seed)
    sim = AstarIslandSimulator.from_round_number(
        round_number,
        queries_max=n_queries,
        seed=rng_seed,
    )
    round_data = sim.get_round(sim.round_id)
    model = IslandModel.from_round_data(round_data, predictor)

    LOGGER.info(
        "Round %d: %dx%d map, %d seeds, %d queries",
        round_number,
        round_data.map_height,
        round_data.map_width,
        round_data.seeds_count,
        n_queries,
    )

    # Run viewport queries distributed across seeds
    if n_queries > 0:
        queries_per_seed = _distribute_queries(n_queries, round_data.seeds_count)
        for seed_idx, seed_n_queries in enumerate(queries_per_seed):
            positions = _pick_viewport_positions(
                round_data.map_height,
                round_data.map_width,
                seed_n_queries,
                rng,
            )
            for x, y in positions:
                result = sim.simulate(sim.round_id, seed_idx, x, y)
                model.update(seed_idx, result["grid"], result["x"], result["y"])

        LOGGER.info("Ran %d queries (%s per seed)", n_queries, queries_per_seed)

    # Generate predictions
    predictions: dict[int, NDArray[np.float64]] = {}
    for seed_idx in range(round_data.seeds_count):
        predictions[seed_idx] = model.predict(seed_idx)

    # Score
    scores = sim.score(predictions)
    avg_score = sim.score_average(predictions)
    LOGGER.info("Average score: %.1f", avg_score)

    # Create experiment directory and save artifacts
    exp_name = f"round{round_number:02d}_{predictor_name}_q{n_queries}"
    exp_dir = _create_experiment_dir(exp_name)

    # Save scores as JSON
    results = {
        "round_number": round_number,
        "predictor": predictor_name,
        "n_queries": n_queries,
        "rng_seed": rng_seed,
        "scores": {str(k): v for k, v in scores.items()},
        "average_score": avg_score,
        "rules": model.rules.summary(),
    }
    (exp_dir / "results.json").write_text(json.dumps(results, indent=2))

    # Save heatmaps per seed
    for seed_idx in range(round_data.seeds_count):
        _save_heatmaps(
            exp_dir,
            seed_idx,
            ground_truth=sim.ground_truth[seed_idx],
            predictions=predictions[seed_idx],
        )

    # Save score summary chart
    _save_score_summary(exp_dir, scores, avg_score)

    LOGGER.info("Experiment saved to %s", exp_dir)
    return exp_dir


def _build_predictor(name: str, ground_truth: NDArray[np.float64] | None = None) -> IslandPredictor:
    """Build a predictor by name."""
    if name == "diffusion":
        from astar_island.predictor import DiffusionPredictor  # noqa: PLC0415

        return DiffusionPredictor()
    if name == "empty":
        from astar_island.predictor import EmptyPredictor  # noqa: PLC0415

        return EmptyPredictor()
    if name == "uniform":
        from astar_island.predictor import UniformPredictor  # noqa: PLC0415

        return UniformPredictor()
    if name == "perfect":
        from astar_island.predictor import PerfectPredictor  # noqa: PLC0415

        if ground_truth is None:
            msg = "PerfectPredictor requires ground truth"
            raise ValueError(msg)
        return PerfectPredictor(ground_truth)

    msg = f"Unknown predictor: {name!r}. Choose from: diffusion, empty, uniform, perfect"
    raise ValueError(msg)


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Run Astar Island offline experiment")
    parser.add_argument("--round", type=int, required=True, help="Round number")
    parser.add_argument(
        "--predictor",
        default="diffusion",
        choices=["diffusion", "empty", "uniform", "perfect"],
        help="Predictor to benchmark (default: diffusion)",
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=0,
        help="Number of viewport queries (default: 0)",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    args = parser.parse_args()

    # Load ground truth for PerfectPredictor
    ground_truth = None
    if args.predictor == "perfect":
        from astar_island.fetch_data import load_round  # noqa: PLC0415

        data = load_round(args.round)
        ground_truth = data["ground_truth"]

    predictor = _build_predictor(args.predictor, ground_truth)

    run_experiment(
        round_number=args.round,
        predictor=predictor,
        predictor_name=args.predictor,
        n_queries=args.queries,
        rng_seed=args.seed,
    )


if __name__ == "__main__":
    main()
