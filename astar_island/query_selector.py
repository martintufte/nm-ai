"""Query selection strategy for Astar Island viewport queries.

Selects queries one at a time, adapting to observed changes. Each call to
select_query() picks the next best query based on the current state.

Selection phases per seed (evaluated in priority order):
  1. Corners (4): (1,1), (1,24), (24,1), (24,24) — first unqueried corner
  2. Edges (4): top/bottom/left/right — pick position maximizing observed
     change from the initial grid
  3. Center (1): pick position in [9,16]x[9,16] maximizing observed change
  4. Flexible (1): anywhere in [3,21]x[3,21] maximizing unobserved dynamic
     cells, tiebreak on observed change

Seeds are selected round-robin so all seeds progress evenly.
"""

import numpy as np
from numpy.typing import NDArray

from astar_island.simulator import VIEWPORT_SIZE

# Corner viewport top-left coordinates
CORNERS = [(1, 1), (1, 24), (24, 1), (24, 24)]

# Edge definitions: (label, x_range, y_range) — one axis is fixed
EDGES = [
    ("top", range(9, 17), range(1, 2)),      # y=1, x varies
    ("bottom", range(9, 17), range(24, 25)),  # y=24, x varies
    ("left", range(1, 2), range(9, 17)),      # x=1, y varies
    ("right", range(24, 25), range(9, 17)),   # x=24, y varies
]

# Search ranges
CENTER_RANGE = range(9, 17)  # [9, 16] inclusive
FLEX_RANGE = range(3, 22)    # [3, 21] inclusive


def _viewport_score(
    grid: NDArray[np.int16],
    changed: NDArray[np.bool_],
    query_counts: NDArray[np.int32],
    x: int,
    y: int,
) -> float:
    """Score a viewport position. Higher is better.

    Balances discovering unobserved cells with re-observing cells that have
    been seen to change. For each dynamic cell:
      - Unobserved cells contribute 1.0 (maximum priority)
      - Observed cells that have ever changed contribute 1/query_count
        (worth re-querying, diminishing with more observations)
      - Observed cells that never changed contribute 0
    """
    region = grid[y : y + VIEWPORT_SIZE, x : x + VIEWPORT_SIZE]
    counts = query_counts[y : y + VIEWPORT_SIZE, x : x + VIEWPORT_SIZE]
    has_changed = changed[y : y + VIEWPORT_SIZE, x : x + VIEWPORT_SIZE]

    dynamic = (region != 10) & (region != 5)
    if not dynamic.any():
        return 0.0

    # Unobserved dynamic cells are worth 1.0 each
    unobserved = dynamic & (counts == 0)

    # Observed dynamic cells that have changed: 1/query_count each
    observed_changed = dynamic & (counts > 0) & has_changed
    requery_value = np.zeros_like(counts, dtype=np.float64)
    requery_value[observed_changed] = 1.0 / counts[observed_changed]

    return float(unobserved.sum()) + float(requery_value.sum())


def _best_position(
    grid: NDArray[np.int16],
    changed: NDArray[np.bool_],
    query_counts: NDArray[np.int32],
    x_range: range,
    y_range: range,
) -> tuple[int, int]:
    """Pick (x, y) from ranges maximizing the viewport score."""
    best_x, best_y = x_range[0], y_range[0]
    best_score = -1.0

    for x in x_range:
        for y in y_range:
            score = _viewport_score(grid, changed, query_counts, x, y)
            if score > best_score:
                best_score = score
                best_x, best_y = x, y

    return best_x, best_y


class QuerySelector:
    """Selects viewport queries one at a time, adapting to observations.

    Tracks per-seed state: which phases are complete, query counts, and
    observed change counts. Call select_query() to get the next query,
    then update() with the viewport result before selecting the next one.
    """

    def __init__(
        self,
        initial_grids: list[NDArray[np.int16]],
        query_counts: dict[int, NDArray[np.int32]],
    ) -> None:
        self._grids = initial_grids
        self._query_counts = query_counts
        self._n_seeds = len(initial_grids)

        # Per-seed change mask: whether each cell has ever been observed
        # to differ from the initial grid value (boolean)
        h, w = initial_grids[0].shape
        self._changed: dict[int, NDArray[np.bool_]] = {
            i: np.zeros((h, w), dtype=np.bool_) for i in range(self._n_seeds)
        }

        # Per-seed phase tracking
        self._corner_idx: dict[int, int] = dict.fromkeys(range(self._n_seeds), 0)
        self._edge_idx: dict[int, int] = dict.fromkeys(range(self._n_seeds), 0)
        self._center_done: dict[int, bool] = dict.fromkeys(range(self._n_seeds), False)

        # Round-robin seed index
        self._next_seed = 0

    def update(
        self,
        seed_index: int,
        x: int,
        y: int,
        observed_grid: NDArray[np.int16],
    ) -> None:
        """Update change counts after observing a viewport result.

        Args:
            seed_index: Which seed was queried.
            x: Viewport top-left x.
            y: Viewport top-left y.
            observed_grid: The observed (vh, vw) grid from the viewport.
        """
        vh, vw = observed_grid.shape
        initial_region = self._grids[seed_index][y : y + vh, x : x + vw]
        changed = observed_grid != initial_region
        self._changed[seed_index][y : y + vh, x : x + vw] |= changed

    def select_query(self) -> tuple[int, int, int]:
        """Return the next (seed_index, x, y) query.

        Cycles through seeds round-robin. For each seed, progresses through
        phases: corners -> edges -> center -> flexible (repeats indefinitely).
        The caller is responsible for stopping when the query budget is exhausted.
        """
        seed = self._next_seed
        self._next_seed = (self._next_seed + 1) % self._n_seeds
        return self._select_for_seed(seed)

    def _select_for_seed(self, seed: int) -> tuple[int, int, int]:
        """Select the next query for a single seed."""
        grid = self._grids[seed]
        changed = self._changed[seed]
        counts = self._query_counts[seed]

        # Phase 1: Corners
        if self._corner_idx[seed] < len(CORNERS):
            x, y = CORNERS[self._corner_idx[seed]]
            self._corner_idx[seed] += 1
            return (seed, x, y)

        # Phase 2: Edges — pick position maximizing change
        if self._edge_idx[seed] < len(EDGES):
            _, x_range, y_range = EDGES[self._edge_idx[seed]]
            self._edge_idx[seed] += 1
            x, y = _best_position(grid, changed, counts, x_range, y_range)
            return (seed, x, y)

        # Phase 3: Center
        if not self._center_done[seed]:
            self._center_done[seed] = True
            x, y = _best_position(
                grid, changed, counts, CENTER_RANGE, CENTER_RANGE,
            )
            return (seed, x, y)

        # Phase 4: Flexible (repeats) — maximize unobserved + changed cells
        x, y = _best_position(grid, changed, counts, FLEX_RANGE, FLEX_RANGE)
        return (seed, x, y)
