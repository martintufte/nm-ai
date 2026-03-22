"""Parameter fitting for the DiffusionPredictor via maximum likelihood."""

import logging

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from astar_island.model import SeedState
from astar_island.predictor.diffuser import DiffusionParams
from astar_island.predictor.diffuser import SymmetricKernel
from astar_island.predictor.diffuser import TerrainPriors
from astar_island.predictor.diffuser import apply_diffusion
from astar_island.predictor.diffuser import apply_port_conversion
from astar_island.predictor.diffuser import apply_ruin_conversion
from astar_island.predictor.diffuser import build_prior

LOGGER = logging.getLogger(__name__)

# Parameter layout:
#   3 priors x 3 free classes = 9   (settlement, forest, empty_land; port=0 ruin=0 mountain=0)
#   1 settle_range in [3, 12]       (sigmoid-mapped)
#   2 kernel edge weights = 2       (settlement, forest; logit-space for [0, 0.25])
#   1 p_ruin (logit-space)
#   1 p_port (logit-space)
# Total: 14 parameters
_FREE_CLASSES = 3  # [empty, settle, forest] — indices 0,1,4
_FREE_IDX = [0, 1, 4]
N_PRIOR_PARAMS = 3 * _FREE_CLASSES  # 9
N_RANGE_PARAMS = 1  # settle_range
N_KERNEL_PARAMS = 2
N_CONVERSION_PARAMS = 2  # p_ruin, p_port
N_PARAMS = N_PRIOR_PARAMS + N_RANGE_PARAMS + N_KERNEL_PARAMS + N_CONVERSION_PARAMS  # 14

# settle_range bounds
_RANGE_LO = 3.0
_RANGE_HI = 12.0


def _softmax(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Softmax that maps unconstrained reals to a probability simplex."""
    e = np.exp(x - x.max())
    return e / e.sum()


def _log_softmax_inv(p: NDArray[np.float64]) -> NDArray[np.float64]:
    """Inverse of softmax: map simplex probs to unconstrained reals."""
    p = np.clip(p, 1e-8, 1.0)
    return np.log(p)


def _sigmoid(x: float, scale: float = 1.0) -> float:
    """Sigmoid mapping real to (0, scale)."""
    return scale / (1.0 + np.exp(-x))


def _logit(p: float, scale: float = 1.0) -> float:
    """Inverse sigmoid mapping (0, scale) to real."""
    p = np.clip(p / scale, 1e-8, 1.0 - 1e-8)
    return float(np.log(p / (1.0 - p)))


def _pack_prior(prior: NDArray[np.float64]) -> NDArray[np.float64]:
    """Pack a prior (3 free classes: empty, settle, forest)."""
    return _log_softmax_inv(prior[_FREE_IDX])


def _unpack_prior(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Unpack a prior to full 6-class array (port=0, ruin=0, mountain=0)."""
    p3 = _softmax(x)
    full = np.zeros(6)
    for i, idx in enumerate(_FREE_IDX):
        full[idx] = p3[i]
    return full


def pack_params(priors: TerrainPriors, diffusion: DiffusionParams) -> NDArray[np.float64]:
    """Pack priors, decay rates, kernels, and p_port into a flat unconstrained vector."""
    x = np.zeros(N_PARAMS)
    offset = 0

    # 3 priors: settlement, forest, empty_land (3 free classes each)
    for prior in [priors.settlement, priors.forest, priors.empty_land]:
        x[offset : offset + _FREE_CLASSES] = _pack_prior(prior)
        offset += _FREE_CLASSES

    # settle_range via sigmoid
    x[offset] = _logit(priors.settle_range - _RANGE_LO, scale=_RANGE_HI - _RANGE_LO)
    offset += N_RANGE_PARAMS

    # 2 kernel edge weights: settlement (index 1) and forest (index 4)
    # edge in [0, 0.25], use logit with scale=0.25
    for k_idx in [1, 4]:
        k = diffusion.kernels[k_idx]
        x[offset] = _logit(k.edge, scale=0.25)
        offset += 1

    # p_ruin and p_port in logit space
    x[offset] = _logit(diffusion.p_ruin)
    x[offset + 1] = _logit(diffusion.p_port)

    return x


def unpack_params(x: NDArray[np.float64]) -> tuple[TerrainPriors, DiffusionParams]:
    """Unpack a flat unconstrained vector into TerrainPriors and DiffusionParams."""
    offset = 0

    # 3 priors
    prior_arrays = []
    for _ in range(3):
        prior_arrays.append(_unpack_prior(x[offset : offset + _FREE_CLASSES]))
        offset += _FREE_CLASSES

    # settle_range
    settle_range = _RANGE_LO + _sigmoid(x[offset], scale=_RANGE_HI - _RANGE_LO)
    offset += N_RANGE_PARAMS

    priors = TerrainPriors(
        settlement=prior_arrays[0],
        forest=prior_arrays[1],
        empty_land=prior_arrays[2],
        settle_range=float(settle_range),
    )

    # 2 kernel edge weights
    kernels = list(DiffusionParams().kernels)
    for k_idx in [1, 4]:
        edge = _sigmoid(x[offset], scale=0.25)
        kernels[k_idx] = SymmetricKernel(edge=float(edge))
        offset += 1

    # p_ruin and p_port
    p_ruin = _sigmoid(x[offset])
    p_port = _sigmoid(x[offset + 1])

    diffusion = DiffusionParams(kernels=kernels, p_ruin=float(p_ruin), p_port=float(p_port))
    return priors, diffusion


def cross_entropy_loss(
    x: NDArray[np.float64],
    seed_states: list[SeedState],
    observed_probs: list[NDArray[np.float64]],
    query_counts: list[NDArray[np.int32]] | None = None,
    eps: float = 1e-10,
) -> float:
    """Weighted cross-entropy loss on dynamic cells.

    Cells queried more times have more reliable empirical distributions
    and receive proportionally higher weight in the loss.
    """
    priors, diffusion = unpack_params(x)

    total_nll = 0.0
    for i, (state, obs) in enumerate(zip(seed_states, observed_probs, strict=True)):
        static_mask = state.water_mask | state.mountain_mask
        prior = build_prior(state, priors)
        pred = apply_diffusion(prior, diffusion, static_mask, prior)
        pred = apply_ruin_conversion(pred, static_mask, diffusion.p_ruin)
        pred = apply_port_conversion(pred, state.coastal_mask, diffusion.p_port)
        pred = np.clip(pred, eps, 1.0)

        dynamic = ~static_mask

        # Per-cell cross-entropy: -sum(obs * log(pred)) per cell
        ce = -np.sum(obs * np.log(pred), axis=-1)  # (H, W)

        if query_counts is not None:
            # Weight by query count: cells observed more are more reliable
            weights = query_counts[i].astype(np.float64)
            total_nll += float(np.sum(ce[dynamic] * weights[dynamic]))
        else:
            total_nll += float(np.sum(ce[dynamic]))

    return total_nll


def fit_diffusion(
    priors: TerrainPriors,
    diffusion: DiffusionParams,
    seed_states: list[SeedState],
    observed_probs: list[NDArray[np.float64]],
    query_counts: list[NDArray[np.int32]] | None = None,
    max_iter: int = 500,
) -> tuple[TerrainPriors, DiffusionParams]:
    """Optimize priors, kernels, and p_port via weighted cross-entropy.

    Cells queried more times receive higher weight in the loss, reflecting
    their more reliable empirical distributions.

    Args:
        priors: Initial terrain priors.
        diffusion: Initial diffusion parameters.
        seed_states: Initial states for each seed.
        observed_probs: Per-seed (H, W, 6) observed probability arrays.
        query_counts: Per-seed (H, W) query count arrays for weighting.
        max_iter: Maximum optimizer iterations.

    Returns:
        Optimized (TerrainPriors, DiffusionParams).
    """
    x0 = pack_params(priors, diffusion)
    loss0 = cross_entropy_loss(x0, seed_states, observed_probs, query_counts)
    LOGGER.info("Fitting DiffusionPredictor: %d params, initial NLL=%.1f", N_PARAMS, loss0)

    result = minimize(
        cross_entropy_loss,
        x0,
        args=(seed_states, observed_probs, query_counts),
        method="L-BFGS-B",
        options={"maxiter": max_iter, "disp": False},
    )

    fitted_priors, fitted_diffusion = unpack_params(result.x)
    LOGGER.info(
        "Fit complete: NLL %.1f -> %.1f (%d iterations, success=%s, p_port=%.3f)",
        loss0, result.fun, result.nit, result.success, fitted_diffusion.p_port,
    )
    return fitted_priors, fitted_diffusion
