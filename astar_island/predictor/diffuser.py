"""Diffusion-based prediction model for Astar Island.

Builds per-cell priors from terrain type, then applies symmetric 3x3 convolution
kernels to model settlement dynamics. Viewport observations override predictions
in the observed region.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from astar_island.client import N_CLASSES
from astar_island.model import IslandPredictor
from astar_island.model import SeedState

# --- Prior distributions per terrain type ---
# Order: [empty, settlement, port, ruin, forest, mountain]

# Water and mountains are static
PRIOR_WATER = np.array([1.00, 0.00, 0.00, 0.00, 0.00, 0.00])
PRIOR_MOUNTAIN = np.array([0.00, 0.00, 0.00, 0.00, 0.00, 1.00])

# Dynamic priors (mountain class = 0, enforced by rules)
PRIOR_SETTLEMENT = np.array([0.10, 0.30, 0.15, 0.20, 0.25, 0.00])
PRIOR_COASTAL_SETTLEMENT = np.array([0.08, 0.20, 0.30, 0.17, 0.25, 0.00])
PRIOR_FOREST = np.array([0.15, 0.05, 0.02, 0.08, 0.70, 0.00])
PRIOR_EMPTY_LAND = np.array([0.45, 0.12, 0.05, 0.08, 0.30, 0.00])


@dataclass
class SymmetricKernel:
    """3x3 kernel with full up/down and left/right symmetry.

    Layout:
        corner  edge  corner
        edge    center  edge
        corner  edge  corner

    The kernel is normalized to sum to 1.0.
    """

    center: float
    edge: float
    corner: float

    def to_array(self) -> NDArray[np.float64]:
        k = np.array(
            [
                [self.corner, self.edge, self.corner],
                [self.edge, self.center, self.edge],
                [self.corner, self.edge, self.corner],
            ],
        )
        return k / k.sum()


# Identity kernel (no diffusion) — used for static/non-spreading classes
IDENTITY_KERNEL = SymmetricKernel(center=1.0, edge=0.0, corner=0.0)

# Default diffusion kernels per class (index matches terrain class)
DEFAULT_KERNELS = [
    IDENTITY_KERNEL,  # empty: no spread
    SymmetricKernel(center=0.30, edge=0.12, corner=0.08),  # settlement: spreads outward
    IDENTITY_KERNEL,  # port: no spread (formed at coast)
    IDENTITY_KERNEL,  # ruin: no spread (converted from settlement)
    SymmetricKernel(center=0.50, edge=0.10, corner=0.05),  # forest: moderate spread
    IDENTITY_KERNEL,  # mountain: static, no spread
]

DEFAULT_NUM_STEPS = 3


def _convolve2d(arr: NDArray[np.float64], kernel: NDArray[np.float64]) -> NDArray[np.float64]:
    """2D convolution with zero-padding."""
    padded = np.pad(arr, 1, mode="constant", constant_values=0.0)
    result = np.zeros_like(arr)
    for di in range(3):
        for dj in range(3):
            result += kernel[di, dj] * padded[di : di + arr.shape[0], dj : dj + arr.shape[1]]
    return result


def _build_prior(state: SeedState) -> NDArray[np.float64]:
    """Build prior probability array from terrain masks."""
    h, w = state.water_mask.shape
    probs = np.zeros((h, w, N_CLASSES))

    # Static terrain
    probs[state.water_mask] = PRIOR_WATER
    probs[state.mountain_mask] = PRIOR_MOUNTAIN

    # Dynamic terrain
    empty_land = ~(
        state.water_mask | state.mountain_mask | state.settlement_mask | state.forest_mask
    )
    probs[empty_land] = PRIOR_EMPTY_LAND
    probs[state.forest_mask] = PRIOR_FOREST

    # Settlements: coastal vs inland have different port probabilities
    inland_settlement = state.settlement_mask & ~state.coastal_mask
    coastal_settlement = state.settlement_mask & state.coastal_mask
    probs[inland_settlement] = PRIOR_SETTLEMENT
    probs[coastal_settlement] = PRIOR_COASTAL_SETTLEMENT

    return probs


def _apply_diffusion(
    probs: NDArray[np.float64],
    kernels: list[SymmetricKernel],
    num_steps: int,
    static_mask: NDArray[np.bool_],
    static_probs: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Apply per-class kernel diffusion for num_steps iterations."""
    for _ in range(num_steps):
        new_probs = np.zeros_like(probs)
        for c in range(N_CLASSES):
            kernel = kernels[c].to_array()
            new_probs[:, :, c] = _convolve2d(probs[:, :, c], kernel)

        # Renormalize
        sums = new_probs.sum(axis=-1, keepdims=True)
        sums = np.maximum(sums, 1e-10)
        new_probs = new_probs / sums

        # Restore static cells
        new_probs[static_mask] = static_probs[static_mask]
        probs = new_probs

    return probs


class DiffusionPredictor(IslandPredictor):
    """Kernel diffusion prediction model.

    Builds per-cell priors from initial terrain, applies symmetric 3x3
    convolution kernels to model settlement spread, and incorporates
    viewport observations as hard evidence.
    """

    def __init__(
        self,
        kernels: list[SymmetricKernel] | None = None,
        num_steps: int = DEFAULT_NUM_STEPS,
    ) -> None:
        self.kernels = kernels or DEFAULT_KERNELS
        self.num_steps = num_steps

    def predict(self, seed_state: SeedState) -> NDArray[np.float64]:
        static_mask = seed_state.water_mask | seed_state.mountain_mask
        prior = _build_prior(seed_state)

        return _apply_diffusion(
            prior,
            self.kernels,
            self.num_steps,
            static_mask,
            prior,
        )
