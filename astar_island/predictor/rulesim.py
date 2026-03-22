"""Monte Carlo rule-based simulation predictor for Astar Island.

Runs a set of probabilistic rules forward in time across many realizations
to produce per-cell class probabilities. Rules are added incrementally and
verified against replay data.
"""

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import field

import numpy as np
from numpy.typing import NDArray

from astar_island.client import N_CLASSES
from astar_island.model import RAW_VALUE_TO_CLASS
from astar_island.model import IslandPredictor
from astar_island.model import SeedState

# Raw grid value -> class index (same mapping as diffuser)
RAW_TO_CLASS = {
    10: 0,  # water
    11: 0,  # plains
    1: 1,  # settlement
    2: 2,  # port
    3: 3,  # ruin
    4: 4,  # forest
    5: 5,  # mountain
}

# Class index -> raw grid value (for simulation grids, pick one canonical raw value)
CLASS_TO_RAW: dict[int, int] = {
    0: 11,  # plains (default land empty)
    1: 1,  # settlement
    2: 2,  # port
    3: 3,  # ruin
    4: 4,  # forest
    5: 5,  # mountain
}


@dataclass(frozen=True)
class StaticMasks:
    """Precomputed masks from the initial grid."""

    water_mask: NDArray[np.bool_]
    mountain_mask: NDArray[np.bool_]
    coastal_mask: NDArray[np.bool_]

    @classmethod
    def from_grid(cls, grid: NDArray[np.int16], coastal_mask: NDArray[np.bool_]) -> "StaticMasks":
        return cls(
            water_mask=grid == 10,
            mountain_mask=grid == 5,
            coastal_mask=coastal_mask,
        )


class Rule(ABC):
    """Abstract base for a simulation rule."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name."""

    @abstractmethod
    def apply(
        self,
        grids: NDArray[np.int8],
        static: StaticMasks,
        rng: np.random.Generator,
    ) -> None:
        """Mutate (N, H, W) int8 class-index grids in-place for one time step."""

    @abstractmethod
    def describes_transition(self, old_name: str, new_name: str) -> bool:
        """Whether this rule covers a given transition type."""

    @abstractmethod
    def is_possible(
        self,
        x: int,
        y: int,
        step: int,
        prev_grid: NDArray[np.int16],
    ) -> bool:
        """Given the grid state before a transition, could this rule produce it at (x, y)?

        prev_grid is the raw grid (raw tile values) from the frame before the transition.
        """


def _chebyshev_has_neighbor(
    grid: NDArray[np.int16],
    x: int,
    y: int,
    value: int,
    max_dist: int = 1,
) -> tuple[bool, int]:
    """Check if (x, y) has a neighbor with given raw value within Chebyshev distance.

    Returns (found, min_distance). If not found, min_distance is a large number.
    """
    h, w = grid.shape
    min_d = 999
    for dy in range(-max_dist, max_dist + 1):
        for dx in range(-max_dist, max_dist + 1):
            if dx == 0 and dy == 0:
                continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and grid[ny, nx] == value:
                d = max(abs(dx), abs(dy))
                min_d = min(min_d, d)
    return min_d <= max_dist, min_d


class RuinToForest(Rule):
    """A ruin cell adjacent (Chebyshev d<=1) to forest becomes forest with probability p per year."""

    def __init__(self, p: float = 0.1) -> None:
        self.p = p

    @property
    def name(self) -> str:
        return "RuinToForest"

    def apply(
        self,
        grids: NDArray[np.int8],
        static: StaticMasks,
        rng: np.random.Generator,
    ) -> None:
        n, h, w = grids.shape
        ruin_class = 3
        forest_class = 4

        # Find cells that are ruin in any realization
        is_ruin = grids == ruin_class  # (N, H, W)

        # Build forest neighbor mask: for each realization, check if any Chebyshev-1 neighbor is forest
        is_forest = grids == forest_class  # (N, H, W)

        # Pad and check all 8 neighbors
        padded = np.pad(is_forest, ((0, 0), (1, 1), (1, 1)), constant_values=False)
        has_forest_neighbor = np.zeros((n, h, w), dtype=bool)
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dy == 0 and dx == 0:
                    continue
                has_forest_neighbor |= padded[:, 1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]

        # Candidate cells: ruin AND has forest neighbor
        candidates = is_ruin & has_forest_neighbor

        # Roll dice
        rolls = rng.random((n, h, w))
        convert = candidates & (rolls < self.p)

        grids[convert] = forest_class

    def describes_transition(self, old_name: str, new_name: str) -> bool:
        return old_name == "ruin" and new_name == "forest"

    def is_possible(
        self,
        x: int,
        y: int,
        step: int,
        prev_grid: NDArray[np.int16],
    ) -> bool:
        # Cell must be ruin (raw value 3) and have a forest neighbor (raw value 4) at Chebyshev d<=1
        if prev_grid[y, x] != 3:
            return False
        found, _ = _chebyshev_has_neighbor(prev_grid, x, y, value=4, max_dist=1)
        return found


def _raw_grid_to_class_grid(raw: NDArray[np.int16]) -> NDArray[np.int8]:
    """Convert raw grid values to class indices."""
    result = np.zeros(raw.shape, dtype=np.int8)
    for raw_val, cls_idx in RAW_TO_CLASS.items():
        result[raw == raw_val] = cls_idx
    return result


@dataclass
class RuleSimulator:
    """Runs rules forward in time across many realizations."""

    rules: list[Rule]
    n_realizations: int = 1000
    n_years: int = 50

    def simulate(
        self,
        initial_grid: NDArray[np.int16],
        static: StaticMasks,
        rng_seed: int = 42,
    ) -> NDArray[np.float64]:
        """Run Monte Carlo simulation.

        Args:
            initial_grid: (H, W) raw grid values.
            static: Precomputed static masks.
            rng_seed: Seed for reproducibility.

        Returns:
            (H, W, 6) probability array.
        """
        rng = np.random.default_rng(rng_seed)
        h, w = initial_grid.shape

        # Initialize all realizations to the same starting state (class indices)
        class_grid = _raw_grid_to_class_grid(initial_grid)
        grids = np.broadcast_to(class_grid, (self.n_realizations, h, w)).copy()

        # Run simulation
        for _ in range(self.n_years):
            for rule in self.rules:
                rule.apply(grids, static, rng)

        # Count outcomes
        probs = np.zeros((h, w, N_CLASSES), dtype=np.float64)
        for c in range(N_CLASSES):
            probs[:, :, c] = (grids == c).sum(axis=0)
        probs /= self.n_realizations

        return probs


@dataclass
class RuleSimPredictor(IslandPredictor):
    """Wraps RuleSimulator for the IslandModel interface."""

    rules: list[Rule] = field(default_factory=lambda: [RuinToForest(p=0.1)])
    n_realizations: int = 1000
    n_years: int = 50
    rng_seed: int = 42

    def predict(
        self,
        seed_state: SeedState,
    ) -> NDArray[np.float64]:
        h, w = seed_state.water_mask.shape
        initial_grid = self._reconstruct_raw_grid(seed_state, h, w)
        static = StaticMasks.from_grid(initial_grid, seed_state.coastal_mask)

        simulator = RuleSimulator(
            rules=self.rules,
            n_realizations=self.n_realizations,
            n_years=self.n_years,
        )
        return simulator.simulate(initial_grid, static, self.rng_seed)

    def update(
        self,
        seed_state: SeedState,
        probs: NDArray[np.float64],
        viewport_grid: list[list[int]],
        viewport_x: int,
        viewport_y: int,
    ) -> NDArray[np.float64]:
        vp = np.array(viewport_grid, dtype=np.int16)
        vh, vw = vp.shape

        one_hot = np.zeros((vh, vw, N_CLASSES), dtype=np.float64)
        for raw_val, class_idx in RAW_VALUE_TO_CLASS.items():
            mask = vp == raw_val
            one_hot[mask, class_idx] = 1.0

        probs = probs.copy()
        probs[viewport_y : viewport_y + vh, viewport_x : viewport_x + vw] = one_hot
        return probs

    @staticmethod
    def _reconstruct_raw_grid(seed_state: SeedState, h: int, w: int) -> NDArray[np.int16]:
        """Reconstruct raw grid from SeedState masks."""
        grid = np.full((h, w), 11, dtype=np.int16)  # default: plains
        grid[seed_state.water_mask] = 10
        grid[seed_state.mountain_mask] = 5
        grid[seed_state.forest_mask] = 4
        grid[seed_state.settlement_mask] = 1
        return grid
