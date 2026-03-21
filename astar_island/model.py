"""Base interface for Astar Island prediction models."""

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import field

import numpy as np
from numpy.typing import NDArray

from astar_island.client import N_CLASSES
from astar_island.client import RoundData
from astar_island.rules import GameRules


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


def parse_raw_grid(raw_grid: NDArray[np.int_]) -> dict[str, NDArray[np.bool_]]:
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


def create_empty_probs(h: int, w: int, n_seeds: int) -> dict[int, NDArray[np.float64]]:
    """Create initial probability arrays with all mass on the empty class (index 0).

    Args:
        h: Map height.
        w: Map width.
        n_seeds: Number of seeds.

    Returns:
        Dict mapping seed_index to (H, W, 6) arrays with prob 1.0 on class 0.
    """
    probs = {}
    for seed_idx in range(n_seeds):
        p = np.zeros((h, w, N_CLASSES), dtype=np.float64)
        p[:, :, 0] = 1.0
        probs[seed_idx] = p

    return probs


class IslandPredictor(ABC):
    @abstractmethod
    def predict(
        self,
        seed_state: SeedState,
        probs: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Return raw predictions for a seed given its current probability state.

        Rule enforcement and min probability floor are applied by IslandModel.

        Args:
            seed_state: Initial board state for this seed.
            probs: Current (H, W, 6) probability array.

        Returns:
            (H, W, 6) probability array, each cell sums to 1.0.
        """

    @abstractmethod
    def update(
        self,
        seed_state: SeedState,
        probs: NDArray[np.float64],
        viewport_grid: list[list[int]],
        viewport_x: int,
        viewport_y: int,
    ) -> NDArray[np.float64]:
        """Update probability state after observing a viewport query result.

        Args:
            seed_state: Initial board state for this seed.
            probs: Current (H, W, 6) probability array.
            viewport_grid: Observed final-state grid.
            viewport_x: Top-left x coordinate of viewport.
            viewport_y: Top-left y coordinate of viewport.

        Returns:
            Updated (H, W, 6) probability array.
        """


@dataclass
class IslandModel:
    """Holds per-seed state and delegates prediction to an IslandPredictor."""

    initial_states: list[SeedState]
    initial_grids: list[NDArray[np.int16]]
    probs: dict[int, NDArray[np.float64]]
    predictor: IslandPredictor
    rules: GameRules = field(default_factory=GameRules)
    observed_viewports: list[tuple[int, int, int, NDArray[np.int16]]] = field(
        default_factory=list,
    )

    @classmethod
    def from_round_data(cls, round_data: RoundData, predictor: IslandPredictor) -> "IslandModel":
        """Initialize model state for all seeds from round data."""
        h, w = round_data.map_height, round_data.map_width

        initial_states = [
            create_seed_state(seed_idx, seed_data.grid)
            for seed_idx, seed_data in enumerate(round_data.seeds)
        ]
        initial_grids = [seed_data.grid for seed_data in round_data.seeds]

        probs = create_empty_probs(h=h, w=w, n_seeds=round_data.seeds_count)

        return cls(
            initial_states=initial_states,
            initial_grids=initial_grids,
            probs=probs,
            predictor=predictor,
            rules=GameRules(),
        )

    def predict(self, seed_index: int) -> NDArray[np.float64]:
        """Generate predictions for a seed, then enforce rules and min probability."""
        probs = self.predictor.predict(
            seed_state=self.initial_states[seed_index],
            probs=self.probs[seed_index],
        )
        return self.rules.enforce_probs(probs, self.initial_grids[seed_index])

    def update(
        self,
        seed_index: int,
        viewport_grid: list[list[int]],
        viewport_x: int,
        viewport_y: int,
    ) -> None:
        """Update model state after observing a viewport."""
        self.rules.validate(
            initial_grid=self.initial_grids[seed_index],
            viewport_grid=viewport_grid,
            viewport_x=viewport_x,
            viewport_y=viewport_y,
            seed_index=seed_index,
        )
        self.probs[seed_index] = self.predictor.update(
            seed_state=self.initial_states[seed_index],
            probs=self.probs[seed_index],
            viewport_grid=viewport_grid,
            viewport_x=viewport_x,
            viewport_y=viewport_y,
        )
        self.observed_viewports.append(
            (seed_index, viewport_x, viewport_y, np.array(viewport_grid, dtype=np.int16)),
        )
