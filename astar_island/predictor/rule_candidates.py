"""Generic spatial kernel rules and candidate generation."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from astar_island.predictor.rule_eval import ReplayCorpus
from astar_island.predictor.rulesim import Rule
from astar_island.predictor.rulesim import StaticMasks
from astar_island.replay import TILE_NAMES

# Raw values considered static terrain (never change as old_type)
STATIC_RAW_VALUES = {10, 5}  # water, mountain


class SpatialKernelRule(Rule):
    """Generalized spatial rule: old_type -> new_type when trigger_type is within max_dist."""

    def __init__(
        self,
        old_type: int,
        new_type: int,
        trigger_type: int | None = None,
        max_dist: int = 1,
        p: float = 0.1,
    ) -> None:
        self.old_type = old_type
        self.new_type = new_type
        self.trigger_type = trigger_type
        self.max_dist = max_dist
        self.p = p

    @property
    def name(self) -> str:
        old_name = TILE_NAMES.get(self.old_type, str(self.old_type))
        new_name = TILE_NAMES.get(self.new_type, str(self.new_type))
        if self.trigger_type is not None:
            trig_name = TILE_NAMES.get(self.trigger_type, str(self.trigger_type))
            return f"{old_name}To{new_name}_near{trig_name}_d{self.max_dist}"
        return f"{old_name}To{new_name}_unconditional"

    def describes_transition(self, old_name: str, new_name: str) -> bool:
        expected_old = TILE_NAMES.get(self.old_type, str(self.old_type))
        expected_new = TILE_NAMES.get(self.new_type, str(self.new_type))
        return old_name == expected_old and new_name == expected_new

    def is_possible(
        self,
        x: int,
        y: int,
        step: int,
        prev_grid: NDArray[np.int16],
    ) -> bool:
        if prev_grid[y, x] != self.old_type:
            return False
        if self.trigger_type is None:
            return True
        h, w = prev_grid.shape
        for dy in range(-self.max_dist, self.max_dist + 1):
            for dx in range(-self.max_dist, self.max_dist + 1):
                if dx == 0 and dy == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and prev_grid[ny, nx] == self.trigger_type:
                    return True
        return False

    def eligible_mask(self, prev_grid: NDArray[np.int16]) -> NDArray[np.bool_]:
        h, w = prev_grid.shape
        is_old = prev_grid == self.old_type

        if self.trigger_type is None:
            return is_old

        is_trigger = prev_grid == self.trigger_type
        padded = np.pad(is_trigger, self.max_dist, constant_values=False)
        has_trigger_neighbor = np.zeros((h, w), dtype=bool)

        for dy in range(-self.max_dist, self.max_dist + 1):
            for dx in range(-self.max_dist, self.max_dist + 1):
                if dx == 0 and dy == 0:
                    continue
                has_trigger_neighbor |= padded[
                    self.max_dist + dy : self.max_dist + dy + h,
                    self.max_dist + dx : self.max_dist + dx + w,
                ]

        return is_old & has_trigger_neighbor

    def apply(
        self,
        grids: NDArray[np.int8],
        static: StaticMasks,
        rng: np.random.Generator,
    ) -> None:
        from astar_island.predictor.rulesim import RAW_TO_CLASS  # noqa: PLC0415

        n, h, w = grids.shape
        old_class = RAW_TO_CLASS[self.old_type]
        new_class = RAW_TO_CLASS[self.new_type]
        is_old = grids == old_class

        if self.trigger_type is not None:
            trigger_class = RAW_TO_CLASS[self.trigger_type]
            is_trigger = grids == trigger_class
            padded = np.pad(
                is_trigger,
                ((0, 0), (self.max_dist, self.max_dist), (self.max_dist, self.max_dist)),
                constant_values=False,
            )
            has_trigger = np.zeros((n, h, w), dtype=bool)
            for dy in range(-self.max_dist, self.max_dist + 1):
                for dx in range(-self.max_dist, self.max_dist + 1):
                    if dx == 0 and dy == 0:
                        continue
                    has_trigger |= padded[
                        :,
                        self.max_dist + dy : self.max_dist + dy + h,
                        self.max_dist + dx : self.max_dist + dx + w,
                    ]
            candidates = is_old & has_trigger
        else:
            candidates = is_old

        rolls = rng.random((n, h, w))
        convert = candidates & (rolls < self.p)
        grids[convert] = new_class


def generate_candidates(
    corpus: ReplayCorpus,
    max_dist: int = 3,
) -> list[SpatialKernelRule]:
    """Generate candidate rules from observed transitions in replay data."""
    # Collect all observed (old_raw, new_raw) pairs
    observed_pairs: set[tuple[int, int]] = set()
    neighbor_types: set[int] = set()

    for replay in corpus.replays:
        for transitions in replay._transitions:
            for t in transitions:
                if t.old in STATIC_RAW_VALUES:
                    continue
                observed_pairs.add((t.old, t.new))

    # Collect all tile types that appear for use as triggers
    for replay in corpus.replays:
        if replay.frames:
            grid = replay.frames[0].grid
            for val in np.unique(grid):
                neighbor_types.add(int(val))

    candidates: list[SpatialKernelRule] = []

    for old_type, new_type in sorted(observed_pairs):
        # Unconditional rule
        candidates.append(
            SpatialKernelRule(
                old_type=old_type,
                new_type=new_type,
                trigger_type=None,
                max_dist=1,
                p=0.1,
            ),
        )

        # Spatial trigger rules
        for trigger_type in sorted(neighbor_types):
            if trigger_type == old_type:
                continue
            candidates.extend(
                SpatialKernelRule(
                    old_type=old_type,
                    new_type=new_type,
                    trigger_type=trigger_type,
                    max_dist=dist,
                    p=0.1,
                )
                for dist in range(1, max_dist + 1)
            )

    return candidates
