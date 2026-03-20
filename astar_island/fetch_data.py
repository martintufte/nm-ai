"""Fetch and store initial states and ground truth from the Astar Island API.

Saves per-round .npz files containing:
- grids: (5, 40, 40) int array of initial grid values
- settlements: list of settlement dicts per seed
- ground_truth: (5, 40, 40, 6) float array (if available from completed rounds)

Grid value mapping to prediction classes:
    10 → class 0 (ocean/water)
    11 → class 0 (plains/empty land)
     1 → class 1 (settlement)
     2 → class 2 (port)
     4 → class 4 (forest)
     5 → class 5 (mountain)

Usage:
    python -m astar_island.fetch_data
"""

import json
import logging
from pathlib import Path

import numpy as np

from astar_island.client import MAP_SIZE
from astar_island.client import NUM_CLASSES
from astar_island.client import NUM_SEEDS
from astar_island.client import AstarIslandClient
from astar_island.config import get_access_token

LOGGER = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"

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


def fetch_round_data(
    client: AstarIslandClient,
    round_id: str,
    round_number: int,
) -> Path:
    """Fetch and save initial states + ground truth for a round."""
    round_data = client.get_round(round_id)

    # Parse initial grids and settlements
    raw_grids = np.zeros((NUM_SEEDS, MAP_SIZE, MAP_SIZE), dtype=np.int16)
    class_grids = np.zeros((NUM_SEEDS, MAP_SIZE, MAP_SIZE), dtype=np.int8)
    all_settlements = []

    for seed_idx in range(NUM_SEEDS):
        state = round_data["initial_states"][seed_idx]
        raw_grids[seed_idx] = np.array(state["grid"], dtype=np.int16)
        class_grids[seed_idx] = grid_to_class_map(raw_grids[seed_idx])
        all_settlements.append(state["settlements"])

    # Build per-seed masks from class grids
    water_masks = raw_grids == 10  # only ocean, not plains
    mountain_masks = class_grids == 5
    settlement_masks = class_grids == 1
    port_masks = class_grids == 2
    forest_masks = class_grids == 4
    plains_masks = raw_grids == 11  # empty land (not ocean)

    # Try to fetch ground truth for completed rounds
    ground_truth = np.full((NUM_SEEDS, MAP_SIZE, MAP_SIZE, NUM_CLASSES), np.nan, dtype=np.float64)
    has_ground_truth = False

    if round_data.get("status") == "completed":
        for seed_idx in range(NUM_SEEDS):
            try:
                analysis = client.get_analysis(round_id, seed_idx)
                if analysis.get("ground_truth") is not None:
                    ground_truth[seed_idx] = np.array(analysis["ground_truth"], dtype=np.float64)
                    has_ground_truth = True
            except Exception:
                LOGGER.warning(
                    "Could not fetch analysis for round %d seed %d",
                    round_number,
                    seed_idx,
                )
                raise

    # Save to .npz
    out_path = DATA_DIR / f"round_{round_number:02d}.npz"
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
    settlements_path = DATA_DIR / f"round_{round_number:02d}_settlements.json"
    settlements_path.write_text(json.dumps(all_settlements, indent=2))

    LOGGER.info(
        "Saved round %d (%s): %d seeds, ground_truth=%s → %s",
        round_number,
        round_id[:8],
        NUM_SEEDS,
        has_ground_truth,
        out_path,
    )
    return out_path


def fetch_all_rounds(client: AstarIslandClient) -> list[Path]:
    """Fetch data for all available rounds."""
    rounds = client.get_rounds()
    paths = []

    for r in sorted(rounds, key=lambda x: x["round_number"]):
        round_id = r["id"]
        round_number = r["round_number"]
        out_path = DATA_DIR / f"round_{round_number:02d}.npz"

        if out_path.exists():
            LOGGER.info("Round %d already saved, skipping", round_number)
            paths.append(out_path)
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
    npz_path = DATA_DIR / f"round_{round_number:02d}.npz"
    data = dict(np.load(npz_path))

    settlements_path = DATA_DIR / f"round_{round_number:02d}_settlements.json"
    if settlements_path.exists():
        data["settlements"] = json.loads(settlements_path.read_text())

    return data


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = AstarIslandClient(token=get_access_token())
    paths = fetch_all_rounds(client)
    LOGGER.info("Fetched %d rounds", len(paths))

    # Print summary of latest round
    latest = sorted(paths)[-1]
    data = np.load(latest)
    for seed_idx in range(NUM_SEEDS):
        grid = data["class_grids"][seed_idx]
        unique, counts = np.unique(grid, return_counts=True)
        class_counts = ", ".join(f"c{v}={c}" for v, c in zip(unique, counts, strict=False))
        LOGGER.info(f"  Seed {seed_idx}: {class_counts}")


if __name__ == "__main__":
    main()
