"""Fetch and store initial states and ground truth from the Astar Island API."""

import json
import logging
from dataclasses import asdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from astar_island.client import N_CLASSES
from astar_island.client import AstarIslandClient
from astar_island.config import get_access_token

LOGGER = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"


def _round_dir(round_number: int) -> Path:
    """Return the directory for a given round."""
    return DATA_DIR / f"round_{round_number:02d}"


# Mapping from API grid values to prediction classes
GRID_VALUE_TO_CLASS = {
    10: 0,  # ocean/water
    11: 0,  # plains/empty land
    1: 1,  # settlement
    2: 2,  # port
    4: 4,  # forest
    5: 5,  # mountain
}


def grid_to_class_map(grid: np.ndarray) -> np.ndarray:
    """Convert raw API grid values to prediction class indices (0-5)."""
    class_map = np.zeros_like(grid, dtype=np.int8)
    for raw_val, class_idx in GRID_VALUE_TO_CLASS.items():
        class_map[grid == raw_val] = class_idx
    return class_map


def _save_seed_plots(
    round_number: int,
    raw_grids: np.ndarray,
    ground_truth: np.ndarray | None,
) -> None:
    """Generate and save per-seed visualizations into the round directory."""
    from astar_island.model import find_coastal_cells  # noqa: PLC0415
    from astar_island.visualize import plot_full_board  # noqa: PLC0415
    from astar_island.visualize import plot_heatmap_combined  # noqa: PLC0415
    from astar_island.visualize import plot_heatmap_grid  # noqa: PLC0415
    from astar_island.visualize import plot_mask_grid  # noqa: PLC0415

    round_dir = _round_dir(round_number)
    n_seeds = raw_grids.shape[0]

    for seed_idx in range(n_seeds):
        seed_dir = round_dir / f"seed_{seed_idx}"
        seed_dir.mkdir(parents=True, exist_ok=True)

        raw_grid = raw_grids[seed_idx]
        water_mask = raw_grid == 10
        plains_mask = raw_grid == 11
        mountain_mask = raw_grid == 5
        settlement_mask = (raw_grid == 1) | (raw_grid == 2)
        forest_mask = raw_grid == 4
        coastal_mask = find_coastal_cells(water_mask)

        # Board overview
        fig, ax = plt.subplots(figsize=(8, 8), facecolor="#1e1e1e")
        plot_full_board(raw_grid, title=f"Round {round_number} — Seed {seed_idx}", ax=ax)
        ax.set_title(ax.get_title(), color="white")
        fig.tight_layout()
        fig.savefig(
            seed_dir / "board.png",
            dpi=150,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )
        plt.close(fig)

        # Terrain masks
        fig = plot_mask_grid(
            raw_grid=raw_grid,
            water_mask=water_mask,
            plains_mask=plains_mask,
            mountain_mask=mountain_mask,
            settlement_mask=settlement_mask,
            forest_mask=forest_mask,
            coastal_mask=coastal_mask,
            suptitle=f"Round {round_number} — Seed {seed_idx} — Terrain Masks",
        )
        fig.savefig(
            seed_dir / "masks.png",
            dpi=150,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )
        plt.close(fig)

        # Ground truth heatmaps
        if ground_truth is not None:
            gt = ground_truth[seed_idx]

            fig = plot_heatmap_grid(
                gt,
                suptitle=f"Round {round_number} — Seed {seed_idx} — Ground Truth",
            )
            fig.savefig(
                seed_dir / "gt_channels.png",
                dpi=150,
                bbox_inches="tight",
                facecolor=fig.get_facecolor(),
            )
            plt.close(fig)

            fig = plot_heatmap_combined(
                gt,
                title=f"Round {round_number} — Seed {seed_idx} — Ground Truth Combined",
            )
            fig.savefig(
                seed_dir / "gt_combined.png",
                dpi=150,
                bbox_inches="tight",
                facecolor=fig.get_facecolor(),
            )
            plt.close(fig)

        LOGGER.info("Saved plots for round %d seed %d", round_number, seed_idx)


def fetch_round_data(
    client: AstarIslandClient,
    round_id: str,
    round_number: int,
) -> Path:
    """Fetch and save initial states + ground truth for a round."""
    round_data = client.get_round(round_id)
    n_seeds = round_data.seeds_count
    h, w = round_data.map_height, round_data.map_width

    # Parse initial grids and settlements
    raw_grids = np.zeros((n_seeds, h, w), dtype=np.int16)
    class_grids = np.zeros((n_seeds, h, w), dtype=np.int8)
    all_settlements = []

    for seed_idx, seed in enumerate(round_data.seeds):
        raw_grids[seed_idx] = seed.grid
        class_grids[seed_idx] = grid_to_class_map(seed.grid)
        all_settlements.append([asdict(s) for s in seed.settlements])

    # Build per-seed masks from class grids
    water_masks = raw_grids == 10  # only ocean, not plains
    mountain_masks = class_grids == 5
    settlement_masks = class_grids == 1
    port_masks = class_grids == 2
    forest_masks = class_grids == 4
    plains_masks = raw_grids == 11  # empty land (not ocean)

    # Try to fetch ground truth for completed rounds
    ground_truth = np.full((n_seeds, h, w, N_CLASSES), np.nan, dtype=np.float64)
    has_ground_truth = False

    if round_data.status == "completed":
        for seed_idx in range(n_seeds):
            try:
                analysis = client.get_analysis(round_id, seed_idx)
                ground_truth[seed_idx] = analysis.ground_truth
                has_ground_truth = True
            except Exception:
                LOGGER.warning(
                    "Could not fetch analysis for round %d seed %d",
                    round_number,
                    seed_idx,
                )
                raise

    # Save to round subdirectory
    round_dir = _round_dir(round_number)
    round_dir.mkdir(parents=True, exist_ok=True)

    out_path = round_dir / "data.npz"
    save_kwargs = {
        "raw_grids": raw_grids,
        "class_grids": class_grids,
        "water_masks": water_masks,
        "mountain_masks": mountain_masks,
        "settlement_masks": settlement_masks,
        "port_masks": port_masks,
        "forest_masks": forest_masks,
        "plains_masks": plains_masks,
    }
    if has_ground_truth:
        save_kwargs["ground_truth"] = ground_truth

    np.savez_compressed(out_path, **save_kwargs)  # ty: ignore[invalid-argument-type]

    # Save settlements as JSON (structured data, not arrays)
    settlements_path = round_dir / "settlements.json"
    settlements_path.write_text(json.dumps(all_settlements, indent=2))

    # Generate per-seed plots
    _save_seed_plots(round_number, raw_grids, ground_truth if has_ground_truth else None)

    LOGGER.info(
        "Saved round %d (%s): %d seeds, ground_truth=%s → %s",
        round_number,
        round_id[:8],
        n_seeds,
        has_ground_truth,
        round_dir,
    )
    return round_dir


def fetch_all_rounds(client: AstarIslandClient) -> list[Path]:
    """Fetch data for all available rounds."""
    rounds = client.get_rounds()
    paths = []

    for r in sorted(rounds, key=lambda x: x["round_number"]):
        round_id = r["id"]
        round_number = r["round_number"]
        round_dir = _round_dir(round_number)

        if (round_dir / "data.npz").exists():
            LOGGER.info("Round %d already saved, skipping", round_number)
            paths.append(round_dir)
            continue

        path = fetch_round_data(client, round_id, round_number)
        paths.append(path)

    return paths


def load_round(round_number: int) -> dict:
    """Load saved round data from disk.

    Returns dict with keys: raw_grids, class_grids, water_masks, mountain_masks,
    settlement_masks, port_masks, forest_masks, plains_masks, and optionally ground_truth.
    Settlements are loaded from the companion JSON file.
    """
    round_dir = _round_dir(round_number)
    data = dict(np.load(round_dir / "data.npz"))

    settlements_path = round_dir / "settlements.json"
    if settlements_path.exists():
        data["settlements"] = json.loads(settlements_path.read_text())

    return data


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = AstarIslandClient(token=get_access_token())
    paths = fetch_all_rounds(client)
    LOGGER.info("Fetched %d rounds", len(paths))


if __name__ == "__main__":
    main()
