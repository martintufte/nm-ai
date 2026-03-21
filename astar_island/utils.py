"""Utility functions for Astar Island."""

import numpy as np
from numpy.typing import NDArray


def sample_final_state(
    probs: NDArray[np.float64],
    rng: np.random.Generator | None = None,
) -> NDArray[np.int8]:
    """Collapse probability distributions into a single deterministic map.

    For each cell, samples one class from the 6-class probability distribution.

    Args:
        probs: (40, 40, 6) probability array.
        rng: Random generator. Uses default if None.

    Returns:
        (40, 40) int8 array with class indices 0-5.
    """
    if rng is None:
        rng = np.random.default_rng()
    h, w, c = probs.shape
    flat = probs.reshape(-1, c)
    # Cumulative sum per cell, then sample via uniform draw
    cumsum = np.cumsum(flat, axis=-1)
    draws = rng.uniform(size=(h * w, 1))
    classes = (draws >= cumsum).sum(axis=-1).astype(np.int8)
    return classes.reshape(h, w)
