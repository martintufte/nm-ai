"""Diffusion-based prediction model for Astar Island.

Builds per-cell priors from terrain type, then applies symmetric 3x3 convolution
kernels to model settlement dynamics. After diffusion, a fraction p_port of
settlement probability on coastal cells is converted to port probability.
"""

from dataclasses import dataclass
from dataclasses import field

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import distance_transform_cdt

from astar_island.client import N_CLASSES
from astar_island.model import IslandPredictor
from astar_island.model import SeedState


@dataclass
class SymmetricKernel:
    """3x3 kernel parameterized by edge weight only.

    Layout:
        0     edge    0
        edge  1-4e    edge
        0     edge    0

    Center is derived as 1 - 4*edge so the kernel sums to 1.
    edge must be in [0, 0.25].
    """

    edge: float

    def to_array(self) -> NDArray[np.float64]:
        e = np.clip(self.edge, 0.0, 0.25)
        c = 1.0 - 4.0 * e
        return np.array(
            [
                [0.0, e, 0.0],
                [e, c, e],
                [0.0, e, 0.0],
            ],
        )


# Identity kernel (no diffusion) — used for static/non-spreading classes
IDENTITY_KERNEL = SymmetricKernel(edge=0.0)


@dataclass
class TerrainPriors:
    """Prior probability distributions per terrain type.

    Order: [empty, settlement, port, ruin, forest, mountain].
    Port and mountain classes should be 0 (port is derived via p_port,
    mountain is enforced by rules).
    """

    water: NDArray[np.float64] = field(
        default_factory=lambda: np.array([1.00, 0.00, 0.00, 0.00, 0.00, 0.00]),
    )
    mountain: NDArray[np.float64] = field(
        default_factory=lambda: np.array([0.00, 0.00, 0.00, 0.00, 0.00, 1.00]),
    )
    settlement: NDArray[np.float64] = field(
        default_factory=lambda: np.array([0.10, 0.40, 0.00, 0.00, 0.50, 0.00]),
    )
    forest: NDArray[np.float64] = field(
        default_factory=lambda: np.array([0.15, 0.05, 0.00, 0.00, 0.80, 0.00]),
    )
    empty_land: NDArray[np.float64] = field(
        default_factory=lambda: np.array([0.50, 0.15, 0.00, 0.00, 0.35, 0.00]),
    )
    # Distance at which empty land becomes pure empty [1,0,0,0,0,0].
    # At d<=1: full empty_land prior. At d>=settle_range: pure empty.
    settle_range: float = 5.0  # tunable in [3, 12]


@dataclass
class DiffusionParams:
    """Parameters for the diffusion step."""

    kernels: list[SymmetricKernel] = field(
        default_factory=lambda: [
            IDENTITY_KERNEL,  # empty: no spread
            SymmetricKernel(edge=0.04),  # settlement
            IDENTITY_KERNEL,  # port: no spread
            IDENTITY_KERNEL,  # ruin: no spread
            SymmetricKernel(edge=0.01),  # forest
            IDENTITY_KERNEL,  # mountain: static
        ],
    )
    n_steps: int = 3
    p_port: float = 0.4  # fraction of settlement prob converted to port on coastal cells
    p_ruin: float = 0.2  # fraction of settlement prob converted to ruin on all dynamic cells


def _convolve2d(arr: NDArray[np.float64], kernel: NDArray[np.float64]) -> NDArray[np.float64]:
    """2D convolution with zero-padding."""
    padded = np.pad(arr, 1, mode="constant", constant_values=0.0)
    result = np.zeros_like(arr)
    for di in range(3):
        for dj in range(3):
            result += kernel[di, dj] * padded[di : di + arr.shape[0], dj : dj + arr.shape[1]]

    return result


def _manhattan_distance(mask: NDArray[np.bool_]) -> NDArray[np.float64]:
    """Compute Manhattan distance from each cell to the nearest True cell.

    Returns 0 at True cells, increasing outward. Uses chessboard/cityblock metric.
    """
    if not mask.any():
        return np.full(mask.shape, 100.0, dtype=np.float64)
    # distance_transform_cdt computes distance from False cells to nearest True cell
    # We invert: pass ~mask so True cells (sources) become the background
    return distance_transform_cdt(~mask, metric="cityblock").astype(np.float64)


def build_prior(state: SeedState, priors: TerrainPriors) -> NDArray[np.float64]:
    """Build prior probability array from terrain masks.

    For empty land cells:
    - Settlement/ruin prob interpolates to 0 based on distance to nearest settlement
    - Forest prob interpolates to 0 based on distance to nearest forest
    - Remaining prob goes to empty class
    """
    h, w = state.water_mask.shape
    probs = np.zeros((h, w, N_CLASSES))

    # Static terrain
    probs[state.water_mask] = priors.water
    probs[state.mountain_mask] = priors.mountain

    # Non-empty terrain types
    probs[state.forest_mask] = priors.forest
    probs[state.settlement_mask] = priors.settlement

    # Empty land: distance-dependent interpolation
    empty_land = ~(
        state.water_mask | state.mountain_mask | state.settlement_mask | state.forest_mask
    )
    if empty_land.any():
        # Start from empty_land prior
        probs[empty_land] = priors.empty_land

        # Settlement influence: scale settle (class 1) by distance to nearest settlement
        dist_settle = _manhattan_distance(state.settlement_mask)
        sr = max(priors.settle_range, 1.01)
        settle_alpha = np.clip((sr - dist_settle[empty_land]) / (sr - 1.0), 0.0, 1.0)
        probs[empty_land, 1] *= settle_alpha

        # Renormalize
        total = probs[empty_land].sum(axis=-1, keepdims=True)
        probs[empty_land] /= np.maximum(total, 1e-10)

    return probs


def apply_diffusion(
    probs: NDArray[np.float64],
    params: DiffusionParams,
    static_mask: NDArray[np.bool_],
    static_probs: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Apply per-class kernel diffusion for n_steps iterations."""
    for _ in range(params.n_steps):
        new_probs = np.zeros_like(probs)
        for c in range(N_CLASSES):
            kernel = params.kernels[c].to_array()
            new_probs[:, :, c] = _convolve2d(probs[:, :, c], kernel)

        # Renormalize
        sums = new_probs.sum(axis=-1, keepdims=True)
        sums = np.maximum(sums, 1e-10)
        new_probs = new_probs / sums

        # Restore static cells
        new_probs[static_mask] = static_probs[static_mask]
        probs = new_probs

    return probs


def apply_port_conversion(
    probs: NDArray[np.float64],
    coastal_mask: NDArray[np.bool_],
    p_port: float,
) -> NDArray[np.float64]:
    """Convert a fraction of settlement probability to port on coastal cells.

    For each coastal cell: port += p_port * settlement, settlement *= (1 - p_port).
    """
    probs = probs.copy()
    settle_coastal = probs[coastal_mask, 1]
    probs[coastal_mask, 2] += p_port * settle_coastal
    probs[coastal_mask, 1] *= 1.0 - p_port
    return probs


def apply_ruin_conversion(
    probs: NDArray[np.float64],
    static_mask: NDArray[np.bool_],
    p_ruin: float,
) -> NDArray[np.float64]:
    """Convert a fraction of settlement probability to ruin on all dynamic cells.

    For each dynamic cell: ruin += p_ruin * settlement, settlement *= (1 - p_ruin).
    """
    probs = probs.copy()
    dynamic = ~static_mask
    settle_dynamic = probs[dynamic, 1]
    probs[dynamic, 3] += p_ruin * settle_dynamic
    probs[dynamic, 1] *= 1.0 - p_ruin
    return probs


class DiffusionPredictor(IslandPredictor):
    """Kernel diffusion prediction model.

    Builds per-cell priors from the initial terrain, applies symmetric 3x3
    convolution kernels to model settlement spread, then converts fractions
    of settlement probability to ruin (all dynamic cells) and port (coastal cells).
    """

    def __init__(
        self,
        terrain_priors: TerrainPriors | None = None,
        diffusion: DiffusionParams | None = None,
    ) -> None:
        self.priors = terrain_priors or TerrainPriors()
        self.diffusion = diffusion or DiffusionParams()

    def predict(self, seed_state: SeedState) -> NDArray[np.float64]:
        static_mask = seed_state.water_mask | seed_state.mountain_mask
        prior = build_prior(seed_state, self.priors)

        probs = apply_diffusion(prior, self.diffusion, static_mask, prior)
        probs = apply_ruin_conversion(probs, static_mask, self.diffusion.p_ruin)
        probs = apply_port_conversion(probs, seed_state.coastal_mask, self.diffusion.p_port)

        return probs

    def fit(
        self,
        seed_states: list[SeedState],
        observed_probs: list[NDArray[np.float64]],
        query_counts: list[NDArray[np.int32]] | None = None,
        max_iter: int = 500,
    ) -> None:
        """Optimize priors and kernels to maximize likelihood of observed probs."""
        from astar_island.predictor.fitting import fit_diffusion  # noqa: PLC0415

        self.priors, self.diffusion = fit_diffusion(
            self.priors,
            self.diffusion,
            seed_states,
            observed_probs,
            query_counts=query_counts,
            max_iter=max_iter,
        )
