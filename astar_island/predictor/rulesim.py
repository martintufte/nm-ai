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
from scipy.ndimage import distance_transform_cdt
from scipy.ndimage import generate_binary_structure as _gen_struct
from scipy.ndimage._nd_image import distance_transform_op as _distance_transform_op

from astar_island.client import N_CLASSES
from astar_island.model import RAW_VALUE_TO_CLASS
from astar_island.model import IslandPredictor
from astar_island.model import SeedState
from astar_island.replay import TILE_NAMES

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

    def eligible_mask(self, prev_grid: NDArray[np.int16]) -> NDArray[np.bool_]:
        """Return (H, W) bool mask of cells where this rule could fire.

        Default implementation calls is_possible() per cell (slow).
        Subclasses should override with vectorized logic.
        """
        h, w = prev_grid.shape
        mask = np.zeros((h, w), dtype=np.bool_)
        for y in range(h):
            for x in range(w):
                mask[y, x] = self.is_possible(x, y, 0, prev_grid)
        return mask


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


_CHEBYSHEV_OFFSETS = [
    (dy, dx) for dy in range(-1, 2) for dx in range(-1, 2) if not (dy == 0 and dx == 0)
]
_MANHATTAN_OFFSETS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

# Precomputed binary structures for scipy distance_transform_cdt
_CDT_STRUCT_CHEBYSHEV = _gen_struct(2, 2)  # 8-connected (chessboard)
_CDT_STRUCT_MANHATTAN = _gen_struct(2, 1)  # 4-connected (cityblock)


def _distance_map(
    source: NDArray[np.bool_],
    max_dist: int,
    metric: str = "chebyshev",
) -> NDArray[np.int32]:
    """Compute distance to nearest True cell, capped at max_dist+1.

    Args:
        source: (H, W) or (N, H, W) boolean mask of source cells.
        max_dist: Maximum distance to compute.
        metric: "chebyshev" (8-connected) or "manhattan" (4-connected).

    Returns:
        Same-shape int32 array. Source cells get 0, unreachable get max_dist+1.
    """
    struct = _CDT_STRUCT_CHEBYSHEV if metric == "chebyshev" else _CDT_STRUCT_MANHATTAN

    if source.ndim == 2:
        dist = distance_transform_cdt(~source, metric=struct).astype(np.int32)
        np.minimum(dist, max_dist + 1, out=dist)
        return dist

    # 3D: loop over realizations, calling C directly to avoid wrapper overhead
    _REVERSE_2D = (slice(None, None, -1), slice(None, None, -1))
    n, _h, _w = source.shape
    dist = np.empty(source.shape, dtype=np.int32)
    for i in range(n):
        dt = np.where(source[i], 0, -1).astype(np.int32)
        _distance_transform_op(struct, dt, None)
        dt = dt[_REVERSE_2D]
        _distance_transform_op(struct, dt, None)
        dist[i] = dt[_REVERSE_2D]
    np.minimum(dist, max_dist + 1, out=dist)
    return dist


def _max_adjacent(
    grid: NDArray[np.floating],  # type: ignore[type-var]
    connectivity: int = 4,
) -> NDArray[np.floating]:  # type: ignore[type-var]
    """For each cell, return the max value among its neighbors.

    Args:
        grid: (H, W) or (N, H, W) float grid.
        connectivity: 4 (Manhattan) or 8 (Chebyshev).

    Returns:
        Same-shape array where each cell holds the max of its neighbors.
    """
    offsets = _MANHATTAN_OFFSETS if connectivity == 4 else _CHEBYSHEV_OFFSETS

    dtype = grid.dtype

    if grid.ndim == 2:
        h, w = grid.shape
        padded = np.pad(grid, 1, constant_values=-np.inf)
        result = np.full((h, w), -np.inf, dtype=dtype)
        for dy, dx in offsets:
            result = np.maximum(result, padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w])
        result[result == -np.inf] = 0.0
        return result

    # 3D: (N, H, W)
    n, h, w = grid.shape
    padded = np.pad(grid, ((0, 0), (1, 1), (1, 1)), constant_values=-np.inf)
    result = np.full((n, h, w), -np.inf, dtype=dtype)
    for dy, dx in offsets:
        result = np.maximum(result, padded[:, 1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w])
    result[result == -np.inf] = 0.0
    return result


def _has_neighbor_mask(
    grid_2d: NDArray[np.bool_],
    max_dist: int,
) -> NDArray[np.bool_]:
    """Vectorized Chebyshev neighbor check for a 2D boolean grid.

    Uses iterative dilation: max_dist iterations of 8-neighbor OR,
    giving max_dist * 8 ops instead of (2d+1)^2 - 1 ops.
    """
    h, w = grid_2d.shape
    result = grid_2d.copy()
    for _ in range(max_dist):
        padded = np.pad(result, 1, constant_values=False)
        for dy, dx in _CHEBYSHEV_OFFSETS:
            result |= padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    return result


def _has_neighbor_mask_3d(
    grid_3d: NDArray[np.bool_],
    max_dist: int,
) -> NDArray[np.bool_]:
    """Vectorized Chebyshev neighbor check for (N, H, W) boolean grids.

    Uses iterative dilation: max_dist iterations of 8-neighbor OR,
    giving max_dist * 8 ops instead of (2d+1)^2 - 1 ops.
    """
    _n, h, w = grid_3d.shape
    result = grid_3d.copy()
    for _ in range(max_dist):
        padded = np.pad(result, ((0, 0), (1, 1), (1, 1)), constant_values=False)
        for dy, dx in _CHEBYSHEV_OFFSETS:
            result |= padded[:, 1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    return result


def RuinToForest(
    a: float = 0.2005,
    b: float = 0.0928,
    metric: str = "manhattan",
) -> "KernelSpawnRule":
    """Ruin near forest becomes forest. Replay-fitted: nearly flat decay (b~0.09)."""
    return KernelSpawnRule(
        3,
        4,
        source_raw=4,
        a=a,
        b=b,
        max_dist=5,
        metric=metric,
        rule_name="RuinToForest",
    )


class UnconditionalRule(Rule):
    """Generic unconditional rule: old_type -> new_type at probability p per step."""

    # Raw grid value -> tile name for display
    _RAW_NAMES = TILE_NAMES

    def __init__(self, old_raw: int, new_raw: int, p: float, rule_name: str | None = None) -> None:
        self.old_raw = old_raw
        self.new_raw = new_raw
        self.p = p
        self._name = (
            rule_name
            or f"{self._RAW_NAMES.get(old_raw, str(old_raw))}To{self._RAW_NAMES.get(new_raw, str(new_raw)).capitalize()}"
        )
        self._old_class = RAW_TO_CLASS[old_raw]
        self._new_class = RAW_TO_CLASS[new_raw]
        self._old_name = self._RAW_NAMES.get(old_raw, str(old_raw))
        self._new_name = self._RAW_NAMES.get(new_raw, str(new_raw))

    @property
    def name(self) -> str:
        return self._name

    def apply(
        self,
        grids: NDArray[np.int8],
        static: StaticMasks,
        rng: np.random.Generator,
    ) -> None:
        n, h, w = grids.shape
        candidates = grids == self._old_class
        # Exclude static cells — water and plains both map to class 0
        static_mask = static.water_mask | static.mountain_mask
        candidates &= ~static_mask[np.newaxis, :, :]
        convert = candidates & (rng.random((n, h, w)) < self.p)
        grids[convert] = self._new_class

    def describes_transition(self, old_name: str, new_name: str) -> bool:
        return old_name == self._old_name and new_name == self._new_name

    def is_possible(self, x: int, y: int, step: int, prev_grid: NDArray[np.int16]) -> bool:
        return prev_grid[y, x] == self.old_raw

    def eligible_mask(self, prev_grid: NDArray[np.int16]) -> NDArray[np.bool_]:
        return prev_grid == self.old_raw


class AdjacentToWaterRule(Rule):
    """Rule that fires on cells of old_type adjacent (Manhattan d=1) to water."""

    def __init__(self, old_raw: int, new_raw: int, p: float, rule_name: str | None = None) -> None:
        self.old_raw = old_raw
        self.new_raw = new_raw
        self.p = p
        old_name = TILE_NAMES.get(old_raw, str(old_raw))
        new_name = TILE_NAMES.get(new_raw, str(new_raw))
        self._name = rule_name or f"{old_name}To{new_name}"
        self._old_class = RAW_TO_CLASS[old_raw]
        self._new_class = RAW_TO_CLASS[new_raw]
        self._old_tile_name = old_name
        self._new_tile_name = new_name

    @property
    def name(self) -> str:
        return self._name

    def apply(
        self,
        grids: NDArray[np.int8],
        static: StaticMasks,
        rng: np.random.Generator,
    ) -> None:
        n, h, w = grids.shape
        is_old = grids == self._old_class
        # 4-adjacent to water (static, same for all realizations)
        adj_water = _has_neighbor_mask(static.water_mask, 1)
        candidates = is_old & adj_water[np.newaxis, :, :]
        convert = candidates & (rng.random((n, h, w)) < self.p)
        grids[convert] = self._new_class

    def describes_transition(self, old_name: str, new_name: str) -> bool:
        return old_name == self._old_tile_name and new_name == self._new_tile_name

    def is_possible(self, x: int, y: int, step: int, prev_grid: NDArray[np.int16]) -> bool:
        if prev_grid[y, x] != self.old_raw:
            return False
        found, _ = _chebyshev_has_neighbor(prev_grid, x, y, value=10, max_dist=1)
        return found

    def eligible_mask(self, prev_grid: NDArray[np.int16]) -> NDArray[np.bool_]:
        is_old = prev_grid == self.old_raw
        is_water = prev_grid == 10
        return is_old & _has_neighbor_mask(is_water, 1)


# Convenience constructors for named unconditional rules
def SettlementToRuin(p: float = 0.0707) -> UnconditionalRule:
    return UnconditionalRule(1, 3, p, "SettlementToRuin")


def RuinToSettlement(p: float = 0.4542) -> UnconditionalRule:
    return UnconditionalRule(3, 1, p, "RuinToSettlement")


def RuinToPlains(p: float = 0.3594) -> UnconditionalRule:
    return UnconditionalRule(3, 11, p, "RuinToPlains")


def PortToRuin(p: float = 0.0488) -> UnconditionalRule:
    return UnconditionalRule(2, 3, p, "PortToRuin")


class KernelSpawnRule(Rule):
    """Spawn rule with exponential probability kernel: p(d) = a * exp(-b * d).

    For each cell of old_type, compute distance to nearest source_type,
    then fire with probability a * exp(-b * d).

    Args:
        metric: "chebyshev" (8-connected) or "manhattan" (4-connected).
    """

    def __init__(
        self,
        old_raw: int,
        new_raw: int,
        source_raw: int | tuple[int, ...],
        a: float,
        b: float,
        max_dist: int = 7,
        metric: str = "manhattan",
        rule_name: str | None = None,
    ) -> None:
        self.old_raw = old_raw
        self.new_raw = new_raw
        self.source_raws = (source_raw,) if isinstance(source_raw, int) else source_raw
        self.a = a
        self.b = b
        self.max_dist = max_dist
        self.metric = metric
        old_name = TILE_NAMES.get(old_raw, str(old_raw))
        new_name = TILE_NAMES.get(new_raw, str(new_raw))
        source_names = "+".join(TILE_NAMES.get(s, str(s)) for s in self.source_raws)
        self._name = rule_name or f"{old_name}To{new_name}_kernel_{source_names}"
        self._old_class = RAW_TO_CLASS[old_raw]
        self._new_class = RAW_TO_CLASS[new_raw]
        self._source_classes = tuple(RAW_TO_CLASS[s] for s in self.source_raws)
        self._old_tile_name = old_name
        self._new_tile_name = new_name

    @property
    def name(self) -> str:
        return self._name

    def __post_init_lut(self) -> None:
        """Build probability lookup table (called lazily)."""
        lut = np.array(
            [self.a * np.exp(-self.b * i) for i in range(self.max_dist + 2)],
            dtype=np.float32,
        )
        lut[-1] = 0.0  # beyond max_dist
        self._p_lut = lut

    def _p_at_dist(self, d: NDArray[np.int32]) -> NDArray[np.float32]:
        """Probability as function of distance (uses precomputed LUT)."""
        if not hasattr(self, "_p_lut"):
            self.__post_init_lut()
        return self._p_lut[d]

    def _source_mask_raw(self, prev_grid: NDArray[np.int16]) -> NDArray[np.bool_]:
        mask = prev_grid == self.source_raws[0]
        for s in self.source_raws[1:]:
            mask |= prev_grid == s
        return mask

    def _source_mask_class(self, grids: NDArray[np.int8]) -> NDArray[np.bool_]:
        mask = grids == self._source_classes[0]
        for c in self._source_classes[1:]:
            mask |= grids == c
        return mask

    def apply(
        self,
        grids: NDArray[np.int8],
        static: StaticMasks,
        rng: np.random.Generator,
    ) -> None:
        is_source = self._source_mask_class(grids)
        dist = _distance_map(is_source, self.max_dist, self.metric)
        in_range = (dist >= 1) & (dist <= self.max_dist)
        p_grid = self._p_at_dist(dist)
        self.apply_with_dist(grids, dist, in_range, p_grid, rng, static)

    def apply_with_dist(
        self,
        grids: NDArray[np.int8],
        dist: NDArray[np.int32],
        in_range: NDArray[np.bool_],
        p_grid: NDArray[np.float32],
        rng: np.random.Generator,
        static: StaticMasks | None = None,
    ) -> None:
        """Apply rule using precomputed distance map, range mask, and probability grid."""
        n, h, w = grids.shape
        candidates = (grids == self._old_class) & in_range
        # Exclude static cells — water and plains both map to class 0
        if static is not None:
            static_mask = static.water_mask | static.mountain_mask
            candidates &= ~static_mask[np.newaxis, :, :]
        convert = candidates & (rng.random((n, h, w), dtype=np.float32) < p_grid)
        grids[convert] = self._new_class

    def describes_transition(self, old_name: str, new_name: str) -> bool:
        return old_name == self._old_tile_name and new_name == self._new_tile_name

    def is_possible(self, x: int, y: int, step: int, prev_grid: NDArray[np.int16]) -> bool:
        if prev_grid[y, x] != self.old_raw:
            return False
        is_source = self._source_mask_raw(prev_grid)
        dist = _distance_map(is_source, self.max_dist, self.metric)
        return 1 <= dist[y, x] <= self.max_dist

    def eligible_mask(self, prev_grid: NDArray[np.int16]) -> NDArray[np.bool_]:
        is_old = prev_grid == self.old_raw
        is_source = self._source_mask_raw(prev_grid)
        dist = _distance_map(is_source, self.max_dist, self.metric)
        return is_old & (dist >= 1) & (dist <= self.max_dist)


class WaterBoostedKernelRule(KernelSpawnRule):
    """Kernel spawn rule with additional water-projected influence.

    Combines a normal distance kernel with a water-masked kernel that lets
    ports project influence further across water.  Coastal land tiles pick
    up the water kernel value from adjacent water neighbors.
    """

    def __init__(
        self,
        old_raw: int,
        new_raw: int,
        source_raw: int | tuple[int, ...],
        a: float,
        b: float,
        a_water: float,
        b_water: float,
        max_dist: int = 7,
        max_dist_water: int = 15,
        metric: str = "manhattan",
        connectivity: int = 4,
        rule_name: str | None = None,
    ) -> None:
        super().__init__(
            old_raw=old_raw,
            new_raw=new_raw,
            source_raw=source_raw,
            a=a,
            b=b,
            max_dist=max_dist,
            metric=metric,
            rule_name=rule_name,
        )
        self.a_water = a_water
        self.b_water = b_water
        self.max_dist_water = max_dist_water
        self.connectivity = connectivity
        # Build water kernel LUT
        self._p_water_lut = np.array(
            [a_water * np.exp(-b_water * i) for i in range(max_dist_water + 2)],
            dtype=np.float32,
        )
        self._p_water_lut[-1] = 0.0

    def _p_water_at_dist(self, d: NDArray[np.int32]) -> NDArray[np.float32]:
        return self._p_water_lut[d]

    def apply(
        self,
        grids: NDArray[np.int8],
        static: StaticMasks,
        rng: np.random.Generator,
    ) -> None:
        n, h, w = grids.shape
        is_old = grids == self._old_class
        is_source = self._source_mask_class(grids)

        # Normal kernel
        dist = _distance_map(is_source, self.max_dist, self.metric)
        p_normal = self._p_at_dist(dist)

        # Water kernel: distance through all cells, then mask to water
        dist_w = _distance_map(is_source, self.max_dist_water, self.metric)
        p_water = self._p_water_at_dist(dist_w)
        # Mask to water tiles only
        water_3d = static.water_mask[np.newaxis, :, :]
        p_water = p_water * water_3d

        # Hop from water to adjacent land
        p_water_land = _max_adjacent(p_water, self.connectivity)
        # Only land tiles benefit from the hop
        p_water_land = p_water_land * (~water_3d)

        # Combine: 1 - (1-p_normal)(1-p_water_land)
        p_combined = np.float32(1.0) - (np.float32(1.0) - p_normal) * (
            np.float32(1.0) - p_water_land.astype(np.float32)
        )

        candidates = is_old & (p_combined > 0)
        convert = candidates & (rng.random((n, h, w), dtype=np.float32) < p_combined)
        grids[convert] = self._new_class

    def apply_with_water_dist(
        self,
        grids: NDArray[np.int8],
        dist_normal: NDArray[np.int32],
        dist_water: NDArray[np.int32],
        static: StaticMasks,
        rng: np.random.Generator,
    ) -> None:
        """Apply rule using precomputed shared distance maps."""
        n, h, w = grids.shape
        is_old = grids == self._old_class
        p_normal = self._p_at_dist(dist_normal)
        p_water = self._p_water_at_dist(dist_water)
        water_3d = static.water_mask[np.newaxis, :, :]
        p_water = p_water * water_3d
        p_water_land = _max_adjacent(p_water, self.connectivity)
        p_water_land = p_water_land * (~water_3d)
        p_combined = np.float32(1.0) - (np.float32(1.0) - p_normal) * (
            np.float32(1.0) - p_water_land.astype(np.float32)
        )
        candidates = is_old & (p_combined > 0)
        convert = candidates & (rng.random((n, h, w), dtype=np.float32) < p_combined)
        grids[convert] = self._new_class

    def is_possible(self, x: int, y: int, step: int, prev_grid: NDArray[np.int16]) -> bool:
        if prev_grid[y, x] != self.old_raw:
            return False
        is_source = self._source_mask_raw(prev_grid)
        # Normal kernel reach
        dist = _distance_map(is_source, self.max_dist, self.metric)
        if 1 <= dist[y, x] <= self.max_dist:
            return True
        # Water kernel reach: check if any adjacent water tile is within water kernel range
        dist_w = _distance_map(is_source, self.max_dist_water, self.metric)
        water_mask = prev_grid == 10
        p_water = self._p_water_at_dist(dist_w)
        p_water = p_water * water_mask
        p_water_land = _max_adjacent(p_water, self.connectivity)
        return p_water_land[y, x] > 0

    def eligible_mask(self, prev_grid: NDArray[np.int16]) -> NDArray[np.bool_]:
        is_old = prev_grid == self.old_raw
        is_source = self._source_mask_raw(prev_grid)
        # Normal kernel eligibility
        dist = _distance_map(is_source, self.max_dist, self.metric)
        normal_elig = (dist >= 1) & (dist <= self.max_dist)
        # Water kernel eligibility
        dist_w = _distance_map(is_source, self.max_dist_water, self.metric)
        water_mask = prev_grid == 10
        p_water = self._p_water_at_dist(dist_w)
        p_water = p_water * water_mask
        p_water_land = _max_adjacent(p_water, self.connectivity)
        water_elig = p_water_land > 0
        return is_old & (normal_elig | water_elig)


# Source: settlement | port (raw values 1, 2)
_SETT_PORT = (1, 2)


def PlainsToSettlement(
    a: float = 0.0269,
    b: float = 0.8399,
    metric: str = "manhattan",
) -> KernelSpawnRule:
    return KernelSpawnRule(
        11,
        1,
        source_raw=_SETT_PORT,
        a=a,
        b=b,
        max_dist=7,
        metric=metric,
        rule_name="PlainsToSettlement",
    )


def ForestToSettlement(
    a: float = 0.0272,
    b: float = 0.8040,
    metric: str = "manhattan",
) -> KernelSpawnRule:
    return KernelSpawnRule(
        4,
        1,
        source_raw=_SETT_PORT,
        a=a,
        b=b,
        max_dist=7,
        metric=metric,
        rule_name="ForestToSettlement",
    )


def PlainsToRuin(
    a: float = 0.0084,
    b: float = 0.7977,
    metric: str = "manhattan",
) -> KernelSpawnRule:
    return KernelSpawnRule(
        11,
        3,
        source_raw=_SETT_PORT,
        a=a,
        b=b,
        max_dist=7,
        metric=metric,
        rule_name="PlainsToRuin",
    )


def ForestToRuin(
    a: float = 0.0105,
    b: float = 0.9515,
    metric: str = "manhattan",
) -> KernelSpawnRule:
    return KernelSpawnRule(
        4,
        3,
        source_raw=_SETT_PORT,
        a=a,
        b=b,
        max_dist=7,
        metric=metric,
        rule_name="ForestToRuin",
    )


def SettlementToPort(p: float = 0.0447) -> "AdjacentToWaterRule":
    """Settlement adjacent (Manhattan d=1) to water becomes port. Replay-verified: only at d=1."""
    return AdjacentToWaterRule(old_raw=1, new_raw=2, p=p, rule_name="SettlementToPort")


def RuinToPort(p: float = 0.1066) -> "AdjacentToWaterRule":
    """Ruin adjacent (Manhattan d=1) to water becomes port. Replay-verified: only at d=1."""
    return AdjacentToWaterRule(old_raw=3, new_raw=2, p=p, rule_name="RuinToPort")


# --- Longboat (water-boosted) convenience constructors ---

_PORT = 2


def LongboatPlainsToSettlement(
    a: float = 0.028,
    b: float = 0.87,
    a_water: float = 0.02,
    b_water: float = 0.15,
    max_dist_water: int = 15,
    connectivity: int = 4,
) -> WaterBoostedKernelRule:
    return WaterBoostedKernelRule(
        11,
        1,
        source_raw=_PORT,
        a=a,
        b=b,
        a_water=a_water,
        b_water=b_water,
        max_dist=7,
        max_dist_water=max_dist_water,
        connectivity=connectivity,
        rule_name=f"LongboatPlainsToSettlement_c{connectivity}_w{max_dist_water}",
    )


def LongboatForestToSettlement(
    a: float = 0.030,
    b: float = 0.87,
    a_water: float = 0.02,
    b_water: float = 0.15,
    max_dist_water: int = 15,
    connectivity: int = 4,
) -> WaterBoostedKernelRule:
    return WaterBoostedKernelRule(
        4,
        1,
        source_raw=_PORT,
        a=a,
        b=b,
        a_water=a_water,
        b_water=b_water,
        max_dist=7,
        max_dist_water=max_dist_water,
        connectivity=connectivity,
        rule_name=f"LongboatForestToSettlement_c{connectivity}_w{max_dist_water}",
    )


def LongboatPlainsToRuin(
    a: float = 0.009,
    b: float = 0.85,
    a_water: float = 0.01,
    b_water: float = 0.15,
    max_dist_water: int = 15,
    connectivity: int = 4,
) -> WaterBoostedKernelRule:
    return WaterBoostedKernelRule(
        11,
        3,
        source_raw=_PORT,
        a=a,
        b=b,
        a_water=a_water,
        b_water=b_water,
        max_dist=7,
        max_dist_water=max_dist_water,
        connectivity=connectivity,
        rule_name=f"LongboatPlainsToRuin_c{connectivity}_w{max_dist_water}",
    )


def LongboatForestToRuin(
    a: float = 0.010,
    b: float = 0.91,
    a_water: float = 0.01,
    b_water: float = 0.15,
    max_dist_water: int = 15,
    connectivity: int = 4,
) -> WaterBoostedKernelRule:
    return WaterBoostedKernelRule(
        4,
        3,
        source_raw=_PORT,
        a=a,
        b=b,
        a_water=a_water,
        b_water=b_water,
        max_dist=7,
        max_dist_water=max_dist_water,
        connectivity=connectivity,
        rule_name=f"LongboatForestToRuin_c{connectivity}_w{max_dist_water}",
    )


def LongboatSettlementToPort(
    a: float = 1.0,
    b: float = 2.92,
    a_water: float = 0.05,
    b_water: float = 0.10,
    max_dist_water: int = 15,
    connectivity: int = 4,
) -> WaterBoostedKernelRule:
    return WaterBoostedKernelRule(
        1,
        2,
        source_raw=_PORT,
        a=a,
        b=b,
        a_water=a_water,
        b_water=b_water,
        max_dist=5,
        max_dist_water=max_dist_water,
        connectivity=connectivity,
        rule_name=f"LongboatSettlementToPort_c{connectivity}_w{max_dist_water}",
    )


def LongboatRuinToPort(
    a: float = 1.0,
    b: float = 2.25,
    a_water: float = 0.05,
    b_water: float = 0.10,
    max_dist_water: int = 15,
    connectivity: int = 4,
) -> WaterBoostedKernelRule:
    return WaterBoostedKernelRule(
        3,
        2,
        source_raw=_PORT,
        a=a,
        b=b,
        a_water=a_water,
        b_water=b_water,
        max_dist=5,
        max_dist_water=max_dist_water,
        connectivity=connectivity,
        rule_name=f"LongboatRuinToPort_c{connectivity}_w{max_dist_water}",
    )


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

        # Pre-group KernelSpawnRules by (source_classes, metric, max_dist)
        # so we compute the distance map once per group per step.
        non_kernel_rules: list[Rule] = []
        kernel_groups: dict[tuple, list[KernelSpawnRule]] = {}
        water_kernel_groups: dict[tuple, list[WaterBoostedKernelRule]] = {}
        for rule in self.rules:
            if isinstance(rule, WaterBoostedKernelRule):
                key = (rule._source_classes, rule.metric, rule.max_dist, rule.max_dist_water)
                water_kernel_groups.setdefault(key, []).append(rule)
            elif isinstance(rule, KernelSpawnRule):
                key = (rule._source_classes, rule.metric, rule.max_dist)
                kernel_groups.setdefault(key, []).append(rule)
            else:
                non_kernel_rules.append(rule)

        # Run simulation
        for _ in range(self.n_years):
            for rule in non_kernel_rules:
                rule.apply(grids, static, rng)
            for (source_classes, metric, max_dist), group in kernel_groups.items():
                # Compute shared source mask, distance map, and range mask
                mask = grids == source_classes[0]
                for c in source_classes[1:]:
                    mask |= grids == c
                dist = _distance_map(mask, max_dist, metric)
                in_range = (dist >= 1) & (dist <= max_dist)
                for rule in group:
                    p_grid = rule._p_at_dist(dist)
                    rule.apply_with_dist(grids, dist, in_range, p_grid, rng, static)
            for (
                source_classes,
                metric,
                max_dist,
                max_dist_water,
            ), group in water_kernel_groups.items():
                # Shared source mask + normal dist + water dist
                mask = grids == source_classes[0]
                for c in source_classes[1:]:
                    mask |= grids == c
                dist_normal = _distance_map(mask, max_dist, metric)
                dist_water = _distance_map(mask, max_dist_water, metric)
                for rule in group:
                    rule.apply_with_water_dist(grids, dist_normal, dist_water, static, rng)

        # Count outcomes
        probs = np.zeros((h, w, N_CLASSES), dtype=np.float64)
        for c in range(N_CLASSES):
            probs[:, :, c] = (grids == c).sum(axis=0)
        probs /= self.n_realizations

        return probs


@dataclass
class RuleSimPredictor(IslandPredictor):
    """Wraps RuleSimulator for the IslandModel interface."""

    rules: list[Rule] = field(
        default_factory=lambda: [
            RuinToForest(),
            SettlementToRuin(),
            RuinToSettlement(),
            RuinToPlains(),
            SettlementToPort(),
            RuinToPort(),
            PortToRuin(),
            PlainsToSettlement(),
            ForestToSettlement(),
            PlainsToRuin(),
            ForestToRuin(),
        ],
    )
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
