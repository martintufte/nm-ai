"""Base interface for Astar Island prediction models."""

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import field

import numpy as np
from numpy.typing import NDArray

from astar_island.client import N_CLASSES
from astar_island.client import RoundData
from astar_island.client import ViewPortData
from astar_island.rules import GameRules

# Mapping from raw grid values to class indices
RAW_VALUE_TO_CLASS = {
    10: 0,  # ocean/water
    11: 0,  # plains/empty land
    1: 1,  # settlement
    2: 2,  # port
    3: 3,  # ruin
    4: 4,  # forest
    5: 5,  # mountain
}


@dataclass
class SeedState:
    """Per-seed initial board state parsed from the raw grid."""

    seed_index: int
    forest_mask: NDArray[np.bool_]
    mountain_mask: NDArray[np.bool_]
    settlement_mask: NDArray[np.bool_]
    water_mask: NDArray[np.bool_]
    coastal_mask: NDArray[np.bool_]


def find_coastal_cells(water_mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
    """Find land cells adjacent (4-connected) to water."""
    coastal = np.zeros_like(water_mask)
    for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        shifted = np.roll(np.roll(water_mask, dy, axis=0), dx, axis=1)
        coastal |= shifted

    return coastal & ~water_mask


def parse_raw_grid(raw_grid: NDArray[np.int16]) -> dict[str, NDArray[np.bool_]]:
    """Parse a raw API grid (values 1, 2, 4, 5, 10, 11) into terrain masks."""
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


def create_seed_state(seed_index: int, raw_grid: NDArray[np.int16]) -> SeedState:
    """Create a SeedState from a raw grid array.

    Args:
        seed_index: Which seed.
        raw_grid: (H, W) array with API values (1, 2, 4, 5, 10, 11).
    """
    masks = parse_raw_grid(raw_grid)
    return SeedState(
        seed_index=seed_index,
        water_mask=masks["water_mask"],
        mountain_mask=masks["mountain_mask"],
        settlement_mask=masks["settlement_mask"],
        forest_mask=masks["forest_mask"],
        coastal_mask=masks["coastal_mask"],
    )


class IslandPredictor(ABC):
    @abstractmethod
    def predict(self, seed_state: SeedState) -> NDArray[np.float64]:
        """Return raw predictions for a seed.

        Rule enforcement and min probability floor are applied by IslandModel.

        Args:
            seed_state: Initial board state for this seed.

        Returns:
            (H, W, 6) probability array, each cell sums to 1.0.
        """

    def fit(  # noqa: B027
        self,
        seed_states: list[SeedState],
        observed_probs: list[NDArray[np.float64]],
        query_counts: list[NDArray[np.int32]] | None = None,
    ) -> None:
        """Fit predictor parameters to observed data. No-op by default."""


@dataclass
class IslandModel:
    """Holds per-seed state and delegates prediction to an IslandPredictor."""

    initial_states: list[SeedState]
    initial_grids: list[NDArray[np.int16]]
    query_counts: dict[int, NDArray[np.int32]]
    predictor: IslandPredictor
    rules: GameRules = field(default_factory=GameRules)
    observed_viewports: list[ViewPortData] = field(default_factory=list)
    _fitted: bool = field(default=True, repr=False)

    @classmethod
    def from_round_data(cls, round_data: RoundData, predictor: IslandPredictor) -> "IslandModel":
        """Initialize model state for all seeds from round data."""
        h, w = round_data.map_height, round_data.map_width

        initial_states = [
            create_seed_state(seed_idx, seed_data.grid)
            for seed_idx, seed_data in enumerate(round_data.seeds)
        ]
        initial_grids = [seed_data.grid for seed_data in round_data.seeds]
        query_counts = {i: np.zeros((h, w), dtype=np.int32) for i in range(round_data.seeds_count)}

        return cls(
            initial_states=initial_states,
            initial_grids=initial_grids,
            query_counts=query_counts,
            predictor=predictor,
            rules=GameRules(),
        )

    def update(self, result: ViewPortData) -> None:
        """Update model state after observing a viewport."""
        self.rules.validate(
            initial_grid=self.initial_grids[result.seed_index],
            viewport_grid=result.grid.tolist(),
            viewport_x=result.viewport_x,
            viewport_y=result.viewport_y,
            seed_index=result.seed_index,
        )

        # Increment per-cell query counter
        self.query_counts[result.seed_index][
            result.viewport_y : result.viewport_y + result.viewport_h,
            result.viewport_x : result.viewport_x + result.viewport_w,
        ] += 1

        self.observed_viewports.append(result)
        self._fitted = False

    def fit(self) -> None:
        """Fit the predictor on observed data from all seeds."""
        if not self.observed_viewports:
            return
        n_seeds = len(self.initial_states)
        obs = [self.observed_probs(i) for i in range(n_seeds)]
        counts = [self.query_counts[i] for i in range(n_seeds)]
        self.predictor.fit(self.initial_states, obs, counts)
        self._fitted = True

    def predict(self, seed_index: int) -> NDArray[np.float64]:
        """Generate predictions for a seed, then enforce rules and min probability.

        Automatically fits the predictor if new observations have been added.
        """
        if not self._fitted and self.observed_viewports:
            self.fit()
        probs = self.predictor.predict(seed_state=self.initial_states[seed_index])
        return self.rules.enforce_probs(probs, self.initial_grids[seed_index])

    def observed_probs(self, seed_index: int) -> NDArray[np.float64]:
        """Build a probability array from observed viewport realizations.

        - Static water cells: [1, 0, 0, 0, 0, 0]
        - Static mountain cells: [0, 0, 0, 0, 0, 1]
        - Observed dynamic cells: average of one-hot realizations across viewports
        - Unobserved dynamic cells: uniform over feasible classes (5 non-mountain)

        Returns:
            (H, W, 6) probability array, each cell sums to 1.0.
        """
        grid = self.initial_grids[seed_index]
        h, w = grid.shape
        counts = self.query_counts[seed_index]

        # Accumulate one-hot class counts from all viewports for this seed
        class_counts = np.zeros((h, w, N_CLASSES), dtype=np.float64)
        for vp in self.observed_viewports:
            if vp.seed_index != seed_index:
                continue
            x, y = vp.viewport_x, vp.viewport_y
            vh, vw = vp.viewport_h, vp.viewport_w
            for raw_val, class_idx in RAW_VALUE_TO_CLASS.items():
                mask = vp.grid == raw_val
                class_counts[y : y + vh, x : x + vw, class_idx] += mask

        # Normalize observed cells by query count
        observed = counts > 0
        probs = np.zeros((h, w, N_CLASSES), dtype=np.float64)

        # Observed cells: empirical average
        obs_counts = counts[observed]
        probs[observed] = class_counts[observed] / obs_counts[:, np.newaxis]

        # Unobserved dynamic cells: uniform over non-mountain classes (5 classes)
        unobserved_dynamic = ~observed & (grid != 10) & (grid != 5)
        probs[unobserved_dynamic] = [0.2, 0.2, 0.2, 0.2, 0.2, 0.0]

        # Static cells: deterministic
        water = grid == 10
        mountain = grid == 5
        probs[water] = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        probs[mountain] = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]

        return self.rules.enforce_probs(probs, grid)
