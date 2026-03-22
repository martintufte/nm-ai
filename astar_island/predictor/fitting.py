"""Generic NLL fitting for IslandPredictor subclasses.

Predictors that support fitting must implement:
  - pack_params() -> NDArray[np.float64]   (serialize to flat unconstrained vector)
  - unpack_params(x: NDArray) -> None       (deserialize and apply to self)
  - predict(seed_state) -> NDArray           (already required by IslandPredictor)

Shared transform utilities (softmax, sigmoid, logit, prior pack/unpack) are
exported for use by individual predictor pack/unpack implementations.
"""

import logging

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from astar_island.model import IslandPredictor
from astar_island.model import SeedState
from astar_island.predictor.diffuser import DiffusionParams
from astar_island.predictor.diffuser import SymmetricKernel
from astar_island.predictor.diffuser import TerrainPriors

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared transform utilities
# ---------------------------------------------------------------------------

# Free classes in prior vectors: [empty, settlement, forest] — indices 0, 1, 4
FREE_CLASSES = 3
FREE_IDX = [0, 1, 4]



def softmax(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Softmax that maps unconstrained reals to a probability simplex."""
    e = np.exp(x - x.max())
    return e / e.sum()


def log_softmax_inv(p: NDArray[np.float64]) -> NDArray[np.float64]:
    """Inverse of softmax: map simplex probs to unconstrained reals."""
    p = np.clip(p, 1e-8, 1.0)
    return np.log(p)


def sigmoid(x: float, scale: float = 1.0) -> float:
    """Sigmoid mapping real to (0, scale)."""
    return scale / (1.0 + np.exp(-x))


def logit(p: float, scale: float = 1.0) -> float:
    """Inverse sigmoid mapping (0, scale) to real."""
    p = np.clip(p / scale, 1e-8, 1.0 - 1e-8)
    return float(np.log(p / (1.0 - p)))


def pack_prior(prior: NDArray[np.float64]) -> NDArray[np.float64]:
    """Pack a 6-class prior to 3 unconstrained reals (free classes only)."""
    return log_softmax_inv(prior[FREE_IDX])


def unpack_prior(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Unpack 3 unconstrained reals to a full 6-class prior."""
    p3 = softmax(x)
    full = np.zeros(6)
    for i, idx in enumerate(FREE_IDX):
        full[idx] = p3[i]
    return full


# ---------------------------------------------------------------------------
# Diffusion parameter pack/unpack (shared by DiffusionPredictor and
# InteractionDiffusionPredictor for their base parameters)
# ---------------------------------------------------------------------------

N_DIFFUSION_PARAMS = 13


def pack_diffusion_params(priors: TerrainPriors, diffusion: DiffusionParams) -> NDArray[np.float64]:
    """Pack (TerrainPriors, DiffusionParams) into 13 unconstrained reals."""
    x = np.zeros(N_DIFFUSION_PARAMS)
    offset = 0

    # 3 priors: settlement, forest, empty_land (3 free classes each = 9)
    for prior in [priors.settlement, priors.forest, priors.empty_land]:
        x[offset : offset + FREE_CLASSES] = pack_prior(prior)
        offset += FREE_CLASSES

    # 2 kernel edge weights: settlement (index 1) and forest (index 4)
    for k_idx in [1, 4]:
        k = diffusion.kernels[k_idx]
        x[offset] = logit(k.edge, scale=0.25)
        offset += 1

    # p_ruin and p_port in logit space
    x[offset] = logit(diffusion.p_ruin)
    x[offset + 1] = logit(diffusion.p_port)

    return x


def unpack_diffusion_params(x: NDArray[np.float64]) -> tuple[TerrainPriors, DiffusionParams]:
    """Unpack 13 unconstrained reals into (TerrainPriors, DiffusionParams).

    settle_range uses the TerrainPriors default (not fitted).
    """
    offset = 0

    # 3 priors
    prior_arrays = []
    for _ in range(3):
        prior_arrays.append(unpack_prior(x[offset : offset + FREE_CLASSES]))
        offset += FREE_CLASSES

    priors = TerrainPriors(
        settlement=prior_arrays[0],
        forest=prior_arrays[1],
        empty_land=prior_arrays[2],
    )

    # 2 kernel edge weights
    kernels = list(DiffusionParams().kernels)
    for k_idx in [1, 4]:
        edge = sigmoid(x[offset], scale=0.25)
        kernels[k_idx] = SymmetricKernel(edge=float(edge))
        offset += 1

    # p_ruin and p_port
    p_ruin = sigmoid(x[offset])
    p_port = sigmoid(x[offset + 1])

    diffusion = DiffusionParams(kernels=kernels, p_ruin=float(p_ruin), p_port=float(p_port))
    return priors, diffusion


# ---------------------------------------------------------------------------
# Generic cross-entropy loss and fitting
# ---------------------------------------------------------------------------


def cross_entropy_loss(
    x: NDArray[np.float64],
    predictor: IslandPredictor,
    seed_states: list[SeedState],
    observed_probs: list[NDArray[np.float64]],
    query_counts: list[NDArray[np.int32]] | None = None,
    eps: float = 1e-10,
) -> float:
    """Weighted cross-entropy loss on dynamic cells.

    Applies x to the predictor via unpack_params, then calls predict() for
    each seed. Cells queried more times receive proportionally higher weight.
    """
    predictor.unpack_params(x)  # type: ignore[attr-defined]

    total_nll = 0.0
    for i, (state, obs) in enumerate(zip(seed_states, observed_probs, strict=True)):
        pred = predictor.predict(state)
        pred = np.clip(pred, eps, 1.0)

        static_mask = state.water_mask | state.mountain_mask
        dynamic = ~static_mask

        # Per-cell cross-entropy: -sum(obs * log(pred)) per cell
        ce = -np.sum(obs * np.log(pred), axis=-1)  # (H, W)

        if query_counts is not None:
            weights = query_counts[i].astype(np.float64)
            total_nll += float(np.sum(ce[dynamic] * weights[dynamic]))
        else:
            total_nll += float(np.sum(ce[dynamic]))

    return total_nll


def fit_predictor(
    predictor: IslandPredictor,
    seed_states: list[SeedState],
    observed_probs: list[NDArray[np.float64]],
    query_counts: list[NDArray[np.int32]] | None = None,
    max_iter: int = 500,
) -> None:
    """Optimize predictor parameters via weighted cross-entropy minimization.

    The predictor must implement pack_params() and unpack_params(x).
    Mutates the predictor in place.
    """
    x0 = predictor.pack_params()  # type: ignore[attr-defined]
    n_params = len(x0)
    loss0 = cross_entropy_loss(x0, predictor, seed_states, observed_probs, query_counts)
    LOGGER.info(
        "Fitting %s: %d params, initial NLL=%.1f",
        type(predictor).__name__,
        n_params,
        loss0,
    )

    result = minimize(
        cross_entropy_loss,
        x0,
        args=(predictor, seed_states, observed_probs, query_counts),
        method="L-BFGS-B",
        options={"maxiter": max_iter, "disp": False},
    )

    # Apply optimized parameters
    predictor.unpack_params(result.x)  # type: ignore[attr-defined]
    LOGGER.info(
        "Fit complete: NLL %.1f -> %.1f (%d iterations, success=%s)",
        loss0,
        result.fun,
        result.nit,
        result.success,
    )
