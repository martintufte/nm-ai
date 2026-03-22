"""Query selection strategy for Astar Island viewport queries.

Selects 50 queries (10 per seed) to maximize information from viewport
observations, prioritizing non-static (dynamic) cells.

Strategy per seed (9 fixed + 1 flexible = 10 queries, 50 total):
  1. Corners (4): (1,1), (1,24), (24,1), (24,24)
  2. Edges (4): fill gaps between corners, pick x or y in [9,16]
     that maximizes dynamic cells
  3. Center (1): pick (x,y) in [9,16]x[9,16] maximizing dynamic cells,
     tiebreak on initial settlements
  4. Flexible (1): anywhere in [3,21]x[3,21] maximizing unobserved
     dynamic cells
"""

import numpy as np
from numpy.typing import NDArray

from astar_island.model import IslandModel
from astar_island.simulator import VIEWPORT_SIZE

# Corner viewport top-left coordinates
CORNERS = [(1, 1), (1, 24), (24, 1), (24, 24)]

# Search ranges for edge/center viewports
EDGE_RANGE = range(9, 17)  # [9, 16] inclusive
FLEX_RANGE = range(3, 22)  # [3, 21] inclusive


def _count_dynamic(
    grid: NDArray[np.int16],
    x: int,
    y: int,
) -> int:
    """Count non-static cells (not water=10, not mountain=5) in a viewport."""
    region = grid[y : y + VIEWPORT_SIZE, x : x + VIEWPORT_SIZE]
    return int(((region != 10) & (region != 5)).sum())


def _count_settlements(
    grid: NDArray[np.int16],
    x: int,
    y: int,
) -> int:
    """Count initial settlement cells (value 1 or 2) in a viewport."""
    region = grid[y : y + VIEWPORT_SIZE, x : x + VIEWPORT_SIZE]
    return int(((region == 1) | (region == 2)).sum())


def _count_unobserved_dynamic(
    grid: NDArray[np.int16],
    query_counts: NDArray[np.int32],
    x: int,
    y: int,
) -> int:
    """Count dynamic cells that have not been observed yet in a viewport."""
    region = grid[y : y + VIEWPORT_SIZE, x : x + VIEWPORT_SIZE]
    counts = query_counts[y : y + VIEWPORT_SIZE, x : x + VIEWPORT_SIZE]
    return int(((region != 10) & (region != 5) & (counts == 0)).sum())


def _best_position(
    grid: NDArray[np.int16],
    x_range: range,
    y_range: range,
    query_counts: NDArray[np.int32] | None = None,
) -> tuple[int, int]:
    """Pick the (x, y) from the given ranges that maximizes dynamic cells.

    If query_counts is provided, only count unobserved dynamic cells.
    Tiebreak on number of initial settlements.
    """
    best_x, best_y = x_range[0], y_range[0]
    best_dynamic = -1
    best_settlements = -1

    for x in x_range:
        for y in y_range:
            if query_counts is not None:
                dynamic = _count_unobserved_dynamic(grid, query_counts, x, y)
            else:
                dynamic = _count_dynamic(grid, x, y)
            settlements = _count_settlements(grid, x, y)

            if dynamic > best_dynamic or (
                dynamic == best_dynamic and settlements > best_settlements
            ):
                best_dynamic = dynamic
                best_settlements = settlements
                best_x, best_y = x, y

    return best_x, best_y


def select_queries(model: IslandModel) -> list[tuple[int, int, int]]:
    """Select 50 viewport queries (10 per seed).

    Returns:
        List of (seed_index, x, y) tuples in execution order.
    """
    queries: list[tuple[int, int, int]] = []
    n_seeds = len(model.initial_states)

    for seed_idx in range(n_seeds):
        grid = model.initial_grids[seed_idx]
        counts = model.query_counts[seed_idx]

        # Phase 1: Corners (4 queries)
        for x, y in CORNERS:
            queries.append((seed_idx, x, y))

        # Phase 2: Edges (4 queries)
        # Top edge: y=1, x varies
        x, _ = _best_position(grid, EDGE_RANGE, range(1, 2))
        queries.append((seed_idx, x, 1))

        # Bottom edge: y=24, x varies
        x, _ = _best_position(grid, EDGE_RANGE, range(24, 25))
        queries.append((seed_idx, x, 24))

        # Left edge: x=1, y varies
        _, y = _best_position(grid, range(1, 2), EDGE_RANGE)
        queries.append((seed_idx, 1, y))

        # Right edge: x=24, y varies
        _, y = _best_position(grid, range(24, 25), EDGE_RANGE)
        queries.append((seed_idx, 24, y))

        # Phase 3: Center (1 query)
        cx, cy = _best_position(grid, EDGE_RANGE, EDGE_RANGE)
        queries.append((seed_idx, cx, cy))

    # Phase 4: Flexible (5 remaining queries — 1 per seed)
    # These are picked considering what's already been queried
    for seed_idx in range(n_seeds):
        grid = model.initial_grids[seed_idx]

        # Build a temporary query_counts reflecting the queries we've planned
        counts = model.query_counts[seed_idx].copy()
        for s, x, y in queries:
            if s == seed_idx:
                counts[y : y + VIEWPORT_SIZE, x : x + VIEWPORT_SIZE] += 1

        fx, fy = _best_position(grid, FLEX_RANGE, FLEX_RANGE, query_counts=counts)
        queries.append((seed_idx, fx, fy))

    return queries
