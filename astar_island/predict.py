"""Astar Island prediction pipeline.

Model:
1. Parse initial maps to identify terrain masks (water, mountain, settlement, forest)
2. Build per-cell prior probabilities based on terrain type
3. Apply symmetric 3x3 convolution kernels over k steps to model settlement dynamics
4. Enforce board symmetry (up/down + left/right)
5. Ensure minimum probability floor and submit

Symmetry assumption: The board has up/down and left/right symmetry, so predictions
are averaged with their horizontal/vertical flips.

Usage:
    python -m astar_island.predict --token YOUR_TOKEN --round-id 1
"""

import argparse
import logging
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from astar_island.client import MAP_SIZE
from astar_island.client import NUM_CLASSES
from astar_island.client import NUM_SEEDS
from astar_island.client import AstarIslandClient

LOGGER = logging.getLogger(__name__)

# --- Prior distributions per terrain type ---
# Order: [empty, settlement, port, ruin, forest, mountain]
# These represent expected probabilities after 50 years of simulation.
PRIOR_WATER = np.array([0.97, 0.005, 0.005, 0.005, 0.005, 0.01])
PRIOR_MOUNTAIN = np.array([0.01, 0.005, 0.005, 0.005, 0.005, 0.97])
PRIOR_SETTLEMENT = np.array([0.10, 0.25, 0.15, 0.25, 0.15, 0.10])
PRIOR_COASTAL_SETTLEMENT = np.array([0.08, 0.15, 0.30, 0.22, 0.15, 0.10])
PRIOR_FOREST = np.array([0.15, 0.05, 0.02, 0.08, 0.65, 0.05])
PRIOR_EMPTY_LAND = np.array([0.40, 0.12, 0.05, 0.13, 0.25, 0.05])

DEFAULT_NUM_STEPS = 3


@dataclass
class SymmetricKernel:
    """3x3 kernel with full up/down and left/right symmetry.

    Layout:
        corner  edge  corner
        edge    center  edge
        corner  edge  corner

    The kernel is normalized to sum to 1.0.
    """

    center: float
    edge: float
    corner: float

    def to_array(self) -> NDArray[np.float64]:
        k = np.array(
            [
                [self.corner, self.edge, self.corner],
                [self.edge, self.center, self.edge],
                [self.corner, self.edge, self.corner],
            ],
        )
        return k / k.sum()


# Identity kernel (no diffusion) — used for static/non-spreading classes
IDENTITY_KERNEL = SymmetricKernel(center=1.0, edge=0.0, corner=0.0)

# Default diffusion kernels per class (index matches terrain class)
DEFAULT_KERNELS = [
    IDENTITY_KERNEL,  # empty: no spread
    SymmetricKernel(center=0.30, edge=0.12, corner=0.08),  # settlement: spreads outward
    IDENTITY_KERNEL,  # port: no spread (formed at coast)
    IDENTITY_KERNEL,  # ruin: no spread (converted from settlement)
    SymmetricKernel(center=0.50, edge=0.10, corner=0.05),  # forest: moderate spread
    IDENTITY_KERNEL,  # mountain: static, no spread
]


@dataclass
class SeedState:
    """Per-seed board state and predictions."""

    seed_index: int
    probs: NDArray[np.float64]  # (40, 40, 6) probability array
    water_mask: NDArray[np.bool_]  # (40, 40) boundary water + lakes
    mountain_mask: NDArray[np.bool_]  # (40, 40) permanent mountains
    settlement_mask: NDArray[np.bool_]  # (40, 40) initial settlements
    forest_mask: NDArray[np.bool_]  # (40, 40) initial forests
    coastal_mask: NDArray[np.bool_]  # (40, 40) land cells adjacent to water


# --- Grid value mapping ---
# API grid values differ from prediction classes
GRID_VALUE_TO_CLASS = {
    10: 0,  # ocean/water
    11: 0,  # plains/empty land
    1: 1,  # settlement
    2: 2,  # port
    4: 4,  # forest
    5: 5,  # mountain
}


# --- Map parsing ---


def find_coastal_cells(water_mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
    """Find land cells adjacent (8-connected) to water."""
    coastal = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    for dy in [-1, 0, 1]:
        for dx in [-1, 0, 1]:
            if dy == 0 and dx == 0:
                continue
            shifted = np.roll(np.roll(water_mask, dy, axis=0), dx, axis=1)
            coastal |= shifted
    return coastal & ~water_mask


def parse_raw_grid(raw_grid: NDArray[np.int_]) -> dict[str, NDArray[np.bool_]]:
    """Parse a raw API grid (values 1,2,4,5,10,11) into terrain masks."""
    water_mask = raw_grid == 10
    plains_mask = raw_grid == 11
    mountain_mask = raw_grid == 5
    settlement_mask = (raw_grid == 1) | (raw_grid == 2)  # settlements + ports
    forest_mask = raw_grid == 4
    coastal_mask = find_coastal_cells(water_mask)
    return {
        "water_mask": water_mask,
        "plains_mask": plains_mask,
        "mountain_mask": mountain_mask,
        "settlement_mask": settlement_mask,
        "forest_mask": forest_mask,
        "coastal_mask": coastal_mask,
    }


def create_seed_state(seed_index: int, raw_grid: list[list[int]]) -> SeedState:
    """Create a SeedState from API initial grid data.

    Args:
        seed_index: Which seed (0-4)
        raw_grid: 40x40 grid with API values (1,2,4,5,10,11)
    """
    grid = np.array(raw_grid, dtype=np.int16)
    masks = parse_raw_grid(grid)
    state = SeedState(
        seed_index=seed_index,
        probs=np.zeros((MAP_SIZE, MAP_SIZE, NUM_CLASSES)),
        water_mask=masks["water_mask"],
        mountain_mask=masks["mountain_mask"],
        settlement_mask=masks["settlement_mask"],
        forest_mask=masks["forest_mask"],
        coastal_mask=masks["coastal_mask"],
    )
    state.probs = build_prior(state)
    return state


# --- Prior construction ---


def build_prior(state: SeedState) -> NDArray[np.float64]:
    """Build prior probability array from terrain masks.

    Assignment order ensures more specific terrain types override generic ones.
    """
    probs = np.zeros((MAP_SIZE, MAP_SIZE, NUM_CLASSES))

    # Static terrain
    probs[state.water_mask] = PRIOR_WATER
    probs[state.mountain_mask] = PRIOR_MOUNTAIN

    # Dynamic terrain
    empty_land = ~(
        state.water_mask | state.mountain_mask | state.settlement_mask | state.forest_mask
    )
    probs[empty_land] = PRIOR_EMPTY_LAND
    probs[state.forest_mask] = PRIOR_FOREST

    # Settlements: coastal vs inland have different port probabilities
    inland_settlement = state.settlement_mask & ~state.coastal_mask
    coastal_settlement = state.settlement_mask & state.coastal_mask
    probs[inland_settlement] = PRIOR_SETTLEMENT
    probs[coastal_settlement] = PRIOR_COASTAL_SETTLEMENT

    return probs


# --- Kernel diffusion ---


def convolve2d(arr: NDArray[np.float64], kernel: NDArray[np.float64]) -> NDArray[np.float64]:
    """2D convolution with zero-padding (no scipy dependency)."""
    padded = np.pad(arr, 1, mode="constant", constant_values=0.0)
    result = np.zeros_like(arr)
    for di in range(3):
        for dj in range(3):
            result += kernel[di, dj] * padded[di : di + arr.shape[0], dj : dj + arr.shape[1]]
    return result


def apply_diffusion_step(
    probs: NDArray[np.float64],
    kernels: list[SymmetricKernel],
    static_mask: NDArray[np.bool_],
    static_probs: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Apply one step of per-class kernel diffusion."""
    new_probs = np.zeros_like(probs)

    for c in range(NUM_CLASSES):
        kernel = kernels[c].to_array()
        new_probs[:, :, c] = convolve2d(probs[:, :, c], kernel)

    # Renormalize
    sums = new_probs.sum(axis=-1, keepdims=True)
    sums = np.maximum(sums, 1e-10)
    new_probs = new_probs / sums

    # Restore static cells (water, mountain) to their fixed priors
    new_probs[static_mask] = static_probs[static_mask]

    return new_probs


def apply_kernels(
    probs: NDArray[np.float64],
    kernels: list[SymmetricKernel],
    num_steps: int,
    static_mask: NDArray[np.bool_],
    static_probs: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Apply diffusion kernels iteratively for num_steps."""
    for _step in range(num_steps):
        probs = apply_diffusion_step(probs, kernels, static_mask, static_probs)
    return probs


# --- Post-processing ---


def enforce_symmetry(probs: NDArray[np.float64]) -> NDArray[np.float64]:
    """Enforce up/down + left/right board symmetry by averaging all 4 reflections."""
    return (probs + np.flip(probs, axis=0) + np.flip(probs, axis=1) + np.flip(probs, (0, 1))) / 4.0


def ensure_min_probability(
    predictions: NDArray[np.float64],
    min_prob: float = 0.01,
) -> NDArray[np.float64]:
    """Ensure all probabilities >= min_prob while maintaining sum = 1.0.

    Iteratively locks low values at min_prob and redistributes the remaining
    budget proportionally among free (unlocked) values. Converges in at most
    NUM_CLASSES iterations.
    """
    predictions = predictions.copy()
    locked = np.zeros_like(predictions, dtype=bool)

    for _ in range(NUM_CLASSES):
        newly_below = (predictions < min_prob) & ~locked
        if not newly_below.any():
            break

        locked |= newly_below
        predictions[newly_below] = min_prob

        locked_count = locked.astype(np.float64).sum(axis=-1, keepdims=True)
        remaining = 1.0 - locked_count * min_prob

        free = ~locked
        free_sum = np.where(free, predictions, 0.0).sum(axis=-1, keepdims=True)
        scale = np.where(free_sum > 0, remaining / free_sum, 0.0)
        predictions = np.where(locked, min_prob, predictions * scale)

    return predictions


# --- Prediction pipeline ---


def predict_seed(
    state: SeedState,
    kernels: list[SymmetricKernel] | None = None,
    num_steps: int = DEFAULT_NUM_STEPS,
) -> NDArray[np.float64]:
    """Generate predictions for a single seed.

    Steps:
    1. Start from prior (already in state.probs)
    2. Apply per-class diffusion kernels for k steps
    3. Enforce board symmetry
    4. Apply minimum probability floor
    """
    if kernels is None:
        kernels = DEFAULT_KERNELS

    static_mask = state.water_mask | state.mountain_mask
    static_probs = state.probs.copy()

    probs = apply_kernels(state.probs, kernels, num_steps, static_mask, static_probs)
    probs = enforce_symmetry(probs)
    probs = ensure_min_probability(probs)

    return probs


def run_prediction_pipeline(
    client: AstarIslandClient,
    round_id: str,
    kernels: list[SymmetricKernel] | None = None,
    num_steps: int = DEFAULT_NUM_STEPS,
) -> list[SeedState]:
    """Full prediction pipeline for a round.

    Returns the list of SeedStates with final predictions.
    """
    round_data = client.get_round(round_id)
    budget = client.get_budget()
    LOGGER.info("Round %s: budget = %s", round_id, budget)

    # Build seed states from initial grids
    seed_states: list[SeedState] = []
    for seed_idx in range(NUM_SEEDS):
        raw_grid = round_data["initial_states"][seed_idx]["grid"]
        state = create_seed_state(seed_idx, raw_grid)
        seed_states.append(state)
        LOGGER.info(
            "Seed %d: %d water, %d mountain, %d settlement, %d forest cells",
            seed_idx,
            state.water_mask.sum(),
            state.mountain_mask.sum(),
            state.settlement_mask.sum(),
            state.forest_mask.sum(),
        )

    # Generate and submit predictions for each seed
    for state in seed_states:
        state.probs = predict_seed(state, kernels, num_steps)
        result = client.submit(round_id=round_id, predictions=state.probs)
        LOGGER.info("Seed %d submission: %s", state.seed_index, result)

    return seed_states


def main() -> None:
    parser = argparse.ArgumentParser(description="Astar Island prediction pipeline")
    parser.add_argument("--token", required=True, help="JWT auth token")
    parser.add_argument("--round-id", required=True, help="Round ID (UUID string)")
    parser.add_argument(
        "--num-steps",
        type=int,
        default=DEFAULT_NUM_STEPS,
        help="Number of diffusion steps",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    client = AstarIslandClient(token=args.token)
    run_prediction_pipeline(client, args.round_id, num_steps=args.num_steps)


if __name__ == "__main__":
    main()
