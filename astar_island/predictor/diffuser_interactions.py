"""Interaction-aware diffusion predictor for Astar Island.

Extends the base diffusion model with terrain interaction effects from the
environment phase:
  - Forest reclamation of ruins (ruins near forests become forest)
  - Settlement rebuilding of ruins (ruins near settlements get rebuilt)
  - Port trade resilience (ports near other ports survive better)

Each interaction is controlled by a weight and range parameter that can be
tuned independently or fitted via NLL optimization.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import distance_transform_cdt

from astar_island.model import IslandPredictor
from astar_island.model import SeedState
from astar_island.predictor.diffuser import DiffusionParams
from astar_island.predictor.diffuser import TerrainPriors
from astar_island.predictor.diffuser import apply_diffusion
from astar_island.predictor.diffuser import apply_port_conversion
from astar_island.predictor.diffuser import apply_ruin_conversion
from astar_island.predictor.diffuser import build_prior


def _manhattan_distance(mask: NDArray[np.bool_]) -> NDArray[np.float64]:
    """Manhattan distance from each cell to nearest True cell. 0 at True cells."""
    if not mask.any():
        return np.full(mask.shape, 100.0, dtype=np.float64)
    return distance_transform_cdt(~mask, metric="cityblock").astype(np.float64)


@dataclass
class InteractionParams:
    """Weights for terrain interaction effects.

    Each weight controls the strength of one interaction. Set to 0 to disable.
    All weights should be in [0, 1].
    """

    # Forest reclamation: ruins near forests become forest over time.
    # Fraction of ruin probability transferred to forest, scaled by proximity.
    forest_reclaim_ruins: float = 0.47
    forest_reclaim_range: float = 12.0  # max manhattan distance for reclamation

    # Settlement rebuilding: ruins near settlements can be rebuilt.
    # Fraction of ruin probability transferred back to settlement.
    settlement_rebuild_ruins: float = 0.63
    settlement_rebuild_range: float = 10.6  # max manhattan distance

    # Port trade resilience: ports near other ports trade - more food/wealth - survive.
    # Reduces ruin conversion for port-adjacent cells.
    # 0 = no effect, 1 = fully suppress ruin for trading ports.
    port_trade_resilience: float = 0.27
    port_trade_range: float = 8.0  # max manhattan distance for trade


def apply_forest_reclamation(
    probs: NDArray[np.float64],
    forest_mask: NDArray[np.bool_],
    static_mask: NDArray[np.bool_],
    weight: float,
    max_range: float,
) -> NDArray[np.float64]:
    """Transfer ruin probability to forest near existing forests.

    The environment phase: "ruins are eventually overtaken by forest growth."
    """
    if weight <= 0:
        return probs
    probs = probs.copy()
    dynamic = ~static_mask
    dist_forest = _manhattan_distance(forest_mask)

    # Proximity factor: 1 at distance 0, 0 at max_range
    proximity = np.clip((max_range - dist_forest) / max(max_range, 1.0), 0.0, 1.0)

    transfer = probs[dynamic, 3] * proximity[dynamic] * weight
    probs[dynamic, 3] -= transfer
    probs[dynamic, 4] += transfer

    return probs


def apply_settlement_rebuild(
    probs: NDArray[np.float64],
    settlement_mask: NDArray[np.bool_],
    coastal_mask: NDArray[np.bool_],
    static_mask: NDArray[np.bool_],
    weight: float,
    max_range: float,
) -> NDArray[np.float64]:
    """Transfer ruin probability back to settlement/port near existing settlements.

    "Nearby thriving settlements may reclaim and rebuild ruined sites.
     Coastal ruins can even be restored as ports."
    """
    if weight <= 0:
        return probs
    probs = probs.copy()
    dynamic = ~static_mask
    dist_settle = _manhattan_distance(settlement_mask)

    proximity = np.clip((max_range - dist_settle) / max(max_range, 1.0), 0.0, 1.0)

    transfer = probs[dynamic, 3] * proximity[dynamic] * weight

    # Coastal ruins rebuild as ports, inland as settlements
    coastal_dynamic = coastal_mask[dynamic]
    port_transfer = transfer * coastal_dynamic.astype(np.float64)
    settle_transfer = transfer * (~coastal_dynamic).astype(np.float64)

    probs[dynamic, 3] -= transfer
    probs[dynamic, 2] += port_transfer
    probs[dynamic, 1] += settle_transfer

    return probs


def apply_port_trade_resilience(
    probs: NDArray[np.float64],
    coastal_mask: NDArray[np.bool_],
    static_mask: NDArray[np.bool_],
    weight: float,
    max_range: float,
) -> NDArray[np.float64]:
    """Reduce ruin probability for ports that can trade with other ports.

    "Ports within range of each other can trade... Trade generates wealth and food."
    Ports near other ports are more resilient.
    """
    if weight <= 0:
        return probs
    probs = probs.copy()
    dynamic = ~static_mask

    # Use port probability as a soft mask for "nearby ports"
    port_prob = probs[:, :, 2]
    # Find cells with meaningful port probability
    port_cells = port_prob > 0.05
    if not port_cells.any():
        return probs

    dist_port = _manhattan_distance(port_cells)
    # Cells within trade range of another port get resilience
    proximity = np.clip((max_range - dist_port) / max(max_range, 1.0), 0.0, 1.0)

    # Only apply to coastal cells (potential ports)
    coastal_dynamic = dynamic & coastal_mask
    ruin_reduction = probs[coastal_dynamic, 3] * proximity[coastal_dynamic] * weight
    probs[coastal_dynamic, 3] -= ruin_reduction
    probs[coastal_dynamic, 2] += ruin_reduction

    return probs


class InteractionDiffusionPredictor(IslandPredictor):
    """Diffusion predictor with terrain interaction effects.

    Pipeline:
      1. Build per-cell priors from initial terrain (same as DiffusionPredictor)
      2. Apply symmetric kernel diffusion
      3. Apply ruin conversion (settlement - ruin)
      4. Apply interaction effects:
         a. Forest reclamation (ruin - forest near forests)
         b. Settlement rebuild (ruin - settlement/port near settlements)
         c. Port trade resilience (reduce ruin for trading ports)
      5. Apply port conversion (settlement - port on coast)
      6. Renormalize

    Parameter vector layout (20 total):
      [0:14)  base diffusion params (same as DiffusionPredictor)
      [14:17) interaction weights (logit-space, 3 params)
      [17:20) interaction ranges (sigmoid-space with scale=12, 3 params)
    """

    # Interaction weight fields (order matters for pack/unpack)
    _WEIGHT_FIELDS: tuple[str, ...] = (
        "forest_reclaim_ruins",
        "settlement_rebuild_ruins",
        "port_trade_resilience",
    )
    _RANGE_FIELDS: tuple[str, ...] = (
        "forest_reclaim_range",
        "settlement_rebuild_range",
        "port_trade_range",
    )
    _RANGE_SCALE = 12.0  # sigmoid scale for range params

    def __init__(
        self,
        terrain_priors: TerrainPriors | None = None,
        diffusion: DiffusionParams | None = None,
        interactions: InteractionParams | None = None,
    ) -> None:
        self.priors = terrain_priors or TerrainPriors()
        self.diffusion = diffusion or DiffusionParams()
        self.interactions = interactions or InteractionParams()

    def pack_params(self) -> NDArray[np.float64]:
        """Serialize all parameters to a flat unconstrained vector (20 params)."""
        from astar_island.predictor.fitting import logit  # noqa: PLC0415
        from astar_island.predictor.fitting import pack_diffusion_params  # noqa: PLC0415

        base = pack_diffusion_params(self.priors, self.diffusion)

        # 3 interaction weights in logit space (0, 1)
        weights = np.array([logit(getattr(self.interactions, f)) for f in self._WEIGHT_FIELDS])

        # 3 interaction ranges in logit space (0, _RANGE_SCALE)
        ranges = np.array(
            [
                logit(getattr(self.interactions, f), scale=self._RANGE_SCALE)
                for f in self._RANGE_FIELDS
            ],
        )

        return np.concatenate([base, weights, ranges])

    def unpack_params(self, x: NDArray[np.float64]) -> None:
        """Deserialize a flat unconstrained vector and apply to self."""
        from astar_island.predictor.fitting import N_DIFFUSION_PARAMS  # noqa: PLC0415
        from astar_island.predictor.fitting import sigmoid  # noqa: PLC0415
        from astar_island.predictor.fitting import unpack_diffusion_params  # noqa: PLC0415

        # Base diffusion params
        self.priors, self.diffusion = unpack_diffusion_params(x[:N_DIFFUSION_PARAMS])

        offset = N_DIFFUSION_PARAMS

        # 3 interaction weights
        for f in self._WEIGHT_FIELDS:
            setattr(self.interactions, f, float(sigmoid(x[offset])))
            offset += 1

        # 3 interaction ranges
        for f in self._RANGE_FIELDS:
            setattr(self.interactions, f, float(sigmoid(x[offset], scale=self._RANGE_SCALE)))
            offset += 1

    def predict(self, seed_state: SeedState) -> NDArray[np.float64]:
        static_mask = seed_state.water_mask | seed_state.mountain_mask
        ix = self.interactions

        # 1. Build priors
        prior = build_prior(seed_state, self.priors)

        # 2. Diffusion
        probs = apply_diffusion(prior, self.diffusion, static_mask, prior)

        # 3. Ruin conversion
        probs = apply_ruin_conversion(probs, static_mask, self.diffusion.p_ruin)

        # 4. Interaction effects
        probs = apply_forest_reclamation(
            probs,
            seed_state.forest_mask,
            static_mask,
            ix.forest_reclaim_ruins,
            ix.forest_reclaim_range,
        )
        probs = apply_settlement_rebuild(
            probs,
            seed_state.settlement_mask,
            seed_state.coastal_mask,
            static_mask,
            ix.settlement_rebuild_ruins,
            ix.settlement_rebuild_range,
        )
        probs = apply_port_trade_resilience(
            probs,
            seed_state.coastal_mask,
            static_mask,
            ix.port_trade_resilience,
            ix.port_trade_range,
        )

        # 5. Port conversion
        probs = apply_port_conversion(probs, seed_state.coastal_mask, self.diffusion.p_port)

        # 6. Renormalize (safety net)
        sums = probs.sum(axis=-1, keepdims=True)
        probs = probs / np.maximum(sums, 1e-10)

        return probs

    def fit(
        self,
        seed_states: list[SeedState],
        observed_probs: list[NDArray[np.float64]],
        query_counts: list[NDArray[np.int32]] | None = None,
        max_iter: int = 500,
    ) -> None:
        """Optimize all 20 parameters jointly via cross-entropy minimization."""
        from astar_island.predictor.fitting import fit_predictor  # noqa: PLC0415

        fit_predictor(self, seed_states, observed_probs, query_counts, max_iter)
