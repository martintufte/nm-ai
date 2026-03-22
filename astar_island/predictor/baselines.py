"""Baseline predictors for Astar Island benchmarking."""

import numpy as np
from numpy.typing import NDArray

from astar_island.client import N_CLASSES
from astar_island.model import IslandPredictor
from astar_island.model import SeedState


class EmptyPredictor(IslandPredictor):
    """Predicts all probability on the empty class (index 0) for every cell.

    This is the simplest possible baseline — equivalent to predicting
    that nothing changes from an empty map.
    """

    def predict(self, seed_state: SeedState) -> NDArray[np.float64]:
        h, w = seed_state.water_mask.shape
        p = np.zeros((h, w, N_CLASSES), dtype=np.float64)
        p[:, :, 0] = 1.0
        return p


class UniformPredictor(IslandPredictor):
    """Predicts a uniform distribution over all 6 classes for every cell.

    Useful as a "no information" baseline — any predictor that scores
    worse than this is actively harmful.
    """

    def predict(self, seed_state: SeedState) -> NDArray[np.float64]:
        h, w = seed_state.water_mask.shape
        return np.full((h, w, N_CLASSES), 1.0 / N_CLASSES, dtype=np.float64)


class PerfectPredictor(IslandPredictor):
    """Returns the ground truth probabilities directly.

    Requires access to the ground truth array (n_seeds, H, W, 6) at
    construction time. Useful as an upper-bound benchmark.
    """

    def __init__(self, ground_truth: NDArray[np.float64]) -> None:
        self.ground_truth = ground_truth

    def predict(self, seed_state: SeedState) -> NDArray[np.float64]:
        return self.ground_truth[seed_state.seed_index].copy()
