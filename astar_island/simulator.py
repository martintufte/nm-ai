"""Offline simulator for benchmarking Astar Island predictors.

Uses saved round data with ground truth to simulate the API. Each call to
`simulate` samples a realization from the ground truth probability distribution,
matching the stochastic nature of the real game.

Usage:
    from astar_island.simulator import AstarIslandSimulator
    sim = AstarIslandSimulator.from_round_number(1, queries_max=20)
    round_data = sim.get_round(sim.round_id)
    result = sim.simulate(sim.round_id, seed_index=0, x=5, y=5)
"""

import logging

import numpy as np
from numpy.typing import NDArray

from astar_island.client import BudgetData
from astar_island.client import RoundData
from astar_island.client import SeedData
from astar_island.client import Settlement
from astar_island.fetch_data import load_round
from astar_island.metrics import entropy_weighted_kl_score

LOGGER = logging.getLogger(__name__)

VIEWPORT_SIZE = 15

# Class index to raw grid value (inverse of VIEWPORT_VALUE_TO_CLASS)
CLASS_TO_RAW_VALUE = {
    0: 11,  # empty → plains
    1: 1,   # settlement
    2: 2,   # port
    3: 3,   # ruin
    4: 4,   # forest
    5: 5,   # mountain
}


class AstarIslandSimulator:
    """Offline simulator that replaces AstarIslandClient for benchmarking.

    Loads saved round data with ground truth and simulates viewport queries
    by sampling from the ground truth distribution.
    """

    def __init__(
        self,
        round_id: str,
        round_number: int,
        raw_grids: NDArray[np.int16],
        ground_truth: NDArray[np.float64],
        settlements: list[list[dict]],
        queries_max: int = 20,
        rng: np.random.Generator | None = None,
    ) -> None:
        """Initialize simulator from pre-loaded arrays.

        Args:
            round_id: Synthetic round ID string.
            round_number: Round number.
            raw_grids: (n_seeds, H, W) initial grids.
            ground_truth: (n_seeds, H, W, 6) ground truth probabilities.
            settlements: Per-seed list of settlement dicts.
            queries_max: Maximum number of simulate calls allowed.
            rng: Random number generator for reproducible sampling.
        """
        self.round_id = round_id
        self.round_number = round_number
        self.raw_grids = raw_grids
        self.ground_truth = ground_truth
        self.settlements = settlements
        self.queries_max = queries_max
        self.queries_used = 0
        self.rng = rng or np.random.default_rng()

        self.n_seeds, self.h, self.w = raw_grids.shape

    @classmethod
    def from_round_number(
        cls,
        round_number: int,
        queries_max: int = 20,
        seed: int | None = None,
    ) -> "AstarIslandSimulator":
        """Load a saved round and create a simulator.

        Args:
            round_number: Which round to load (must have ground truth).
            queries_max: Maximum number of simulate calls allowed.
            seed: RNG seed for reproducible sampling.
        """
        data = load_round(round_number)

        if "ground_truth" not in data:
            msg = f"Round {round_number} has no ground truth data"
            raise ValueError(msg)

        settlements = data.get("settlements", [[] for _ in range(data["raw_grids"].shape[0])])

        return cls(
            round_id=f"sim-round-{round_number:02d}",
            round_number=round_number,
            raw_grids=data["raw_grids"],
            ground_truth=data["ground_truth"],
            settlements=settlements,
            queries_max=queries_max,
            rng=np.random.default_rng(seed),
        )

    def get_round(self, round_id: str) -> RoundData:
        """Return round data matching the real API response."""
        seeds = []
        for seed_idx in range(self.n_seeds):
            settlement_list = [
                Settlement(
                    x=s["x"],
                    y=s["y"],
                    has_port=s["has_port"],
                    alive=s["alive"],
                )
                for s in self.settlements[seed_idx]
            ]
            seeds.append(SeedData(grid=self.raw_grids[seed_idx], settlements=settlement_list))

        return RoundData(
            id=round_id,
            round_number=self.round_number,
            status="active",
            map_width=self.w,
            map_height=self.h,
            seeds_count=self.n_seeds,
            seeds=seeds,
        )

    def get_budget(self) -> BudgetData:
        """Return current query budget."""
        return BudgetData(
            round_id=self.round_id,
            queries_used=self.queries_used,
            queries_max=self.queries_max,
            active=self.queries_used < self.queries_max,
        )

    def simulate(self, round_id: str, seed_index: int, x: int, y: int) -> dict:
        """Sample a viewport realization from the ground truth distribution.

        Args:
            round_id: Round ID (must match self.round_id).
            seed_index: Which seed to observe.
            x: Top-left x coordinate of viewport.
            y: Top-left y coordinate of viewport.

        Returns:
            Dict with "grid" (list[list[int]]) matching the real API format.

        Raises:
            ValueError: If budget is exhausted or coordinates are out of bounds.
        """
        if self.queries_used >= self.queries_max:
            msg = f"Query budget exhausted ({self.queries_max}/{self.queries_max})"
            raise ValueError(msg)

        if seed_index < 0 or seed_index >= self.n_seeds:
            msg = f"Invalid seed_index {seed_index}, must be in [0, {self.n_seeds})"
            raise ValueError(msg)

        # Clamp viewport to map bounds
        x = max(0, min(x, self.w - VIEWPORT_SIZE))
        y = max(0, min(y, self.h - VIEWPORT_SIZE))

        # Extract ground truth probabilities for this viewport
        gt_region = self.ground_truth[seed_index, y : y + VIEWPORT_SIZE, x : x + VIEWPORT_SIZE]

        # Sample a class for each cell from the ground truth distribution
        sampled_classes = _sample_from_probs(gt_region, self.rng)

        # Convert class indices to raw grid values
        grid = _classes_to_raw_grid(sampled_classes)

        self.queries_used += 1
        LOGGER.debug(
            "Simulate seed=%d viewport=(%d,%d) — query %d/%d",
            seed_index, x, y, self.queries_used, self.queries_max,
        )

        return {
            "grid": grid.tolist(),
            "x": x,
            "y": y,
        }

    def score(self, predictions: dict[int, NDArray[np.float64]]) -> dict[int, float]:
        """Score predictions against ground truth for all seeds.

        Args:
            predictions: Dict mapping seed_index to (H, W, 6) prediction arrays.

        Returns:
            Dict mapping seed_index to score in [0, 100].
        """
        scores = {}
        for seed_idx, preds in predictions.items():
            scores[seed_idx] = entropy_weighted_kl_score(
                ground_truth=self.ground_truth[seed_idx],
                predictions=preds,
            )
        return scores

    def score_average(self, predictions: dict[int, NDArray[np.float64]]) -> float:
        """Return the average score across all seeds."""
        scores = self.score(predictions)
        return float(np.mean(list(scores.values())))


def _sample_from_probs(
    probs: NDArray[np.float64],
    rng: np.random.Generator,
) -> NDArray[np.int8]:
    """Sample class indices from a (H, W, N_CLASSES) probability array."""
    h, w, n = probs.shape
    flat_probs = probs.reshape(-1, n)

    # Cumulative distribution for vectorized sampling
    cumsum = np.cumsum(flat_probs, axis=-1)
    u = rng.random(h * w)[:, np.newaxis]
    sampled = (u < cumsum).argmax(axis=-1).astype(np.int8)

    return sampled.reshape(h, w)


def _classes_to_raw_grid(classes: NDArray[np.int8]) -> NDArray[np.int16]:
    """Convert class indices (0-5) to raw API grid values."""
    grid = np.zeros_like(classes, dtype=np.int16)
    for class_idx, raw_val in CLASS_TO_RAW_VALUE.items():
        grid[classes == class_idx] = raw_val
    return grid
