"""Fit RuleSimPredictor parameters to viewport samples by maximum likelihood.

Each Rule has a probability parameter p. Rules interact because they compete
for the same cells (e.g., RuinToForest, RuinToSettlement, RuinToPlains all
act on ruins), so they must be fit jointly through the full MC simulation.

The log-likelihood of observed viewport cells under the model is:
    LL = sum_{viewports} sum_{cells} log(prob[y, x, observed_class])

where prob comes from running the full RuleSimulator with all rules.

Usage:
    uv run python -m astar_island.fit
    uv run python -m astar_island.fit --rounds 1-16 --n-realizations 2000
"""

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from astar_island.fetch_data import load_round
from astar_island.model import RAW_VALUE_TO_CLASS
from astar_island.model import create_seed_state
from astar_island.predictor.rulesim import ForestToRuin
from astar_island.predictor.rulesim import ForestToSettlement
from astar_island.predictor.rulesim import PlainsToRuin
from astar_island.predictor.rulesim import PlainsToSettlement
from astar_island.predictor.rulesim import PortToRuin
from astar_island.predictor.rulesim import RuinToForest
from astar_island.predictor.rulesim import RuinToPlains
from astar_island.predictor.rulesim import RuinToPort
from astar_island.predictor.rulesim import RuinToSettlement
from astar_island.predictor.rulesim import Rule
from astar_island.predictor.rulesim import RuleSimulator
from astar_island.predictor.rulesim import SettlementToPort
from astar_island.predictor.rulesim import SettlementToRuin
from astar_island.predictor.rulesim import StaticMasks
from astar_island.simulator import AstarIslandSimulator

LOGGER = logging.getLogger(__name__)

EXPERIMENTS_DIR = Path(__file__).parent / "experiments"

# Parameter names in order, matching the vector layout.
# UnconditionalRules / AdjacentToWaterRules have a single p; KernelSpawnRules have (a, b).
PARAM_NAMES = [
    "RuinToForest.a",
    "RuinToForest.b",
    "SettlementToRuin.p",
    "RuinToSettlement.p",
    "RuinToPlains.p",
    "PortToRuin.p",
    "SettlementToPort.p",
    "RuinToPort.p",
    "PlainsToSettlement.a",
    "PlainsToSettlement.b",
    "ForestToSettlement.a",
    "ForestToSettlement.b",
    "PlainsToRuin.a",
    "PlainsToRuin.b",
    "ForestToRuin.a",
    "ForestToRuin.b",
]


def _sigmoid(x: float) -> float:
    """Map unconstrained real to (0, 1)."""
    return 1.0 / (1.0 + np.exp(-x))


def _logit(p: float) -> float:
    """Map (0, 1) to unconstrained real."""
    p = np.clip(p, 1e-6, 1.0 - 1e-6)
    return np.log(p / (1.0 - p))


def _softplus(x: float) -> float:
    """Map unconstrained real to (0, inf)."""
    return np.log1p(np.exp(x))


def _inv_softplus(y: float) -> float:
    """Inverse of softplus."""
    return np.log(np.expm1(max(y, 1e-6)))


# Transform type per parameter: 'p' for logit (0,1), 'b' for softplus (0,inf)
_PARAM_TYPES = [
    "p",  # RuinToForest.a
    "b",  # RuinToForest.b
    "p",  # SettlementToRuin.p
    "p",  # RuinToSettlement.p
    "p",  # RuinToPlains.p
    "p",  # PortToRuin.p
    "p",  # SettlementToPort.p
    "p",  # RuinToPort.p
    "p",  # PlainsToSettlement.a
    "b",  # PlainsToSettlement.b
    "p",  # ForestToSettlement.a
    "b",  # ForestToSettlement.b
    "p",  # PlainsToRuin.a
    "b",  # PlainsToRuin.b
    "p",  # ForestToRuin.a
    "b",  # ForestToRuin.b
]


def params_to_vector(params: list[float]) -> NDArray[np.float64]:
    """Convert rule parameters to unconstrained optimization vector.

    p/a values use logit (constrained to (0,1)).
    b values use inv_softplus (constrained to (0,inf)).
    """
    return np.array(
        [
            _logit(v) if t == "p" else _inv_softplus(v)
            for t, v in zip(_PARAM_TYPES, params, strict=True)
        ],
    )


def vector_to_params(x: NDArray[np.float64]) -> list[float]:
    """Convert unconstrained vector back to rule parameters."""
    return [
        float(_sigmoid(xi)) if t == "p" else float(_softplus(xi))
        for t, xi in zip(_PARAM_TYPES, x, strict=True)
    ]


def build_rules(params: list[float], metric: str = "manhattan") -> list[Rule]:
    """Build rule list from a parameter vector."""
    return [
        RuinToForest(a=params[0], b=params[1], metric=metric),
        SettlementToRuin(p=params[2]),
        RuinToSettlement(p=params[3]),
        RuinToPlains(p=params[4]),
        PortToRuin(p=params[5]),
        SettlementToPort(p=params[6]),
        RuinToPort(p=params[7]),
        PlainsToSettlement(a=params[8], b=params[9], metric=metric),
        ForestToSettlement(a=params[10], b=params[11], metric=metric),
        PlainsToRuin(a=params[12], b=params[13], metric=metric),
        ForestToRuin(a=params[14], b=params[15], metric=metric),
    ]


def default_params() -> list[float]:
    """Return default parameter values from the Rule constructors."""
    rtf = RuinToForest()
    pts = PlainsToSettlement()
    fts = ForestToSettlement()
    ptr = PlainsToRuin()
    ftr = ForestToRuin()
    return [
        rtf.a,
        rtf.b,
        SettlementToRuin().p,
        RuinToSettlement().p,
        RuinToPlains().p,
        PortToRuin().p,
        SettlementToPort().p,
        RuinToPort().p,
        pts.a,
        pts.b,
        fts.a,
        fts.b,
        ptr.a,
        ptr.b,
        ftr.a,
        ftr.b,
    ]


@dataclass
class ViewportSample:
    """A single viewport observation for fitting."""

    seed_index: int
    viewport_x: int
    viewport_y: int
    # (vh, vw) class indices observed
    observed_classes: NDArray[np.int8]


@dataclass
class FitData:
    """Pre-loaded data for fitting: initial grids + viewport samples."""

    # Per-round data
    round_numbers: list[int]
    raw_grids: list[NDArray[np.int16]]  # (n_seeds, H, W) per round

    # Viewport samples collected from simulator
    samples: list[list[ViewportSample]]  # samples[round_idx] = list of ViewportSample

    # Optional ground truth for scoring (not used in likelihood)
    ground_truths: list[NDArray[np.float64] | None]

    @classmethod
    def from_rounds(
        cls,
        round_numbers: list[int],
        n_viewports_per_seed: int = 10,
        rng_seed: int = 42,
    ) -> "FitData":
        """Load rounds and sample viewports from ground truth.

        Args:
            round_numbers: Which rounds to load.
            n_viewports_per_seed: Number of viewport samples per seed.
            rng_seed: RNG seed for reproducible viewport sampling.
        """
        raw_grids_list = []
        gt_list = []
        samples_list = []
        valid_rounds = []

        for rnd in round_numbers:
            data = load_round(rnd)
            if "ground_truth" not in data:
                LOGGER.warning("Round %d has no ground truth, skipping", rnd)
                continue

            raw_grids = data["raw_grids"]
            ground_truth = data["ground_truth"]
            raw_grids_list.append(raw_grids)
            gt_list.append(ground_truth)
            valid_rounds.append(rnd)

            # Sample viewports using the simulator
            sim = AstarIslandSimulator.from_round_number(
                rnd,
                queries_max=raw_grids.shape[0] * n_viewports_per_seed,
                seed=rng_seed,
            )

            round_samples = []
            rng = np.random.default_rng(rng_seed + rnd)
            h, w = raw_grids.shape[1], raw_grids.shape[2]

            for seed_idx in range(raw_grids.shape[0]):
                for _ in range(n_viewports_per_seed):
                    # Random viewport position
                    x = rng.integers(0, w - 15 + 1)
                    y = rng.integers(0, h - 15 + 1)
                    vp = sim.simulate(sim.round_id, seed_idx, x, y)

                    # Convert raw grid to class indices
                    obs_classes = np.zeros_like(vp.grid, dtype=np.int8)
                    for raw_val, cls_idx in RAW_VALUE_TO_CLASS.items():
                        obs_classes[vp.grid == raw_val] = cls_idx

                    round_samples.append(
                        ViewportSample(
                            seed_index=seed_idx,
                            viewport_x=vp.viewport_x,
                            viewport_y=vp.viewport_y,
                            observed_classes=obs_classes,
                        ),
                    )

            samples_list.append(round_samples)

        if not valid_rounds:
            msg = "No rounds with ground truth found"
            raise ValueError(msg)

        LOGGER.info(
            "Loaded %d rounds, %d total viewport samples",
            len(valid_rounds),
            sum(len(s) for s in samples_list),
        )
        return cls(
            round_numbers=valid_rounds,
            raw_grids=raw_grids_list,
            samples=samples_list,
            ground_truths=gt_list,
        )


def log_likelihood(
    params: list[float],
    fit_data: FitData,
    n_realizations: int = 1000,
    n_years: int = 50,
    rng_seed: int = 42,
    eps: float = 1e-12,
    metric: str = "manhattan",
) -> float:
    """Compute total log-likelihood of viewport samples under the model.

    Runs the full MC simulation for each (round, seed) pair, then sums
    log(prob[y, x, observed_class]) over all viewport cells.
    """
    rules = build_rules(params, metric=metric)
    simulator = RuleSimulator(rules=rules, n_realizations=n_realizations, n_years=n_years)

    total_ll = 0.0

    for round_idx in range(len(fit_data.round_numbers)):
        raw_grids = fit_data.raw_grids[round_idx]
        samples = fit_data.samples[round_idx]
        n_seeds = raw_grids.shape[0]

        # Simulate once per seed, reuse for all viewports of that seed
        probs_cache: dict[int, NDArray[np.float64]] = {}

        for seed_idx in range(n_seeds):
            raw_grid = raw_grids[seed_idx]
            seed_state = create_seed_state(seed_idx, raw_grid)
            static = StaticMasks.from_grid(raw_grid, seed_state.coastal_mask)
            probs_cache[seed_idx] = simulator.simulate(raw_grid, static, rng_seed)

        # Score each viewport sample
        for sample in samples:
            probs = probs_cache[sample.seed_index]
            vx, vy = sample.viewport_x, sample.viewport_y
            vh, vw = sample.observed_classes.shape

            # Extract predicted probs for the viewport region
            region_probs = probs[vy : vy + vh, vx : vx + vw]  # (vh, vw, 6)

            # Skip static cells (water/mountain) — they're deterministic and don't
            # depend on rule parameters, so they just add a constant to LL
            raw_region = fit_data.raw_grids[round_idx][sample.seed_index][
                vy : vy + vh,
                vx : vx + vw,
            ]
            dynamic = (raw_region != 10) & (raw_region != 5)

            # Gather predicted probability of the observed class at each dynamic cell
            obs = sample.observed_classes[dynamic]
            pred_probs = region_probs[dynamic]
            # pred_probs[i, obs[i]] is the probability of the observed class
            cell_probs = pred_probs[np.arange(len(obs)), obs]
            total_ll += np.sum(np.log(np.maximum(cell_probs, eps)))

    return total_ll


def fit(
    fit_data: FitData,
    n_realizations: int = 1000,
    n_years: int = 50,
    method: str = "Nelder-Mead",
    maxiter: int = 300,
    rng_seed: int = 42,
    verbose: bool = True,
    metric: str = "manhattan",
) -> tuple[list[float], float]:
    """Fit rule parameters by maximizing log-likelihood of viewport samples.

    Args:
        fit_data: Pre-loaded training data with viewport samples.
        n_realizations: MC realizations per simulation.
        n_years: Simulation steps.
        method: scipy.optimize method.
        maxiter: Maximum iterations.
        rng_seed: RNG seed for simulations.
        verbose: Print progress.
        metric: Distance metric for kernel rules ("manhattan" or "chebyshev").

    Returns:
        (best_params, best_ll) — fitted p values and log-likelihood.
    """
    init_p = default_params()
    x0 = params_to_vector(init_p)

    init_ll = log_likelihood(init_p, fit_data, n_realizations, n_years, rng_seed, metric=metric)
    LOGGER.info("Initial LL: %.2f  params: %s", init_ll, init_p)
    if verbose:
        print(f"Initial LL: {init_ll:.2f}")
        print(f"Initial params: {dict(zip(PARAM_NAMES, init_p, strict=True))}")

    call_count = 0
    best_so_far = [init_ll]

    def objective(x: NDArray[np.float64]) -> float:
        nonlocal call_count
        p = vector_to_params(x)
        ll = log_likelihood(p, fit_data, n_realizations, n_years, rng_seed, metric=metric)
        call_count += 1

        best_so_far[0] = max(best_so_far[0], ll)

        if verbose and call_count % 5 == 0:
            print(f"  eval {call_count:4d}  LL={ll:.2f}  best={best_so_far[0]:.2f}")
        return -ll  # minimize negative LL

    result = minimize(
        objective,
        x0,
        method=method,
        options={"maxiter": maxiter, "xatol": 1e-4, "fatol": 0.5, "adaptive": True},
    )

    best_p = vector_to_params(result.x)
    best_ll = -result.fun

    LOGGER.info("Fit complete: %d evals, LL %.2f → %.2f", result.nfev, init_ll, best_ll)
    if verbose:
        print(f"\nFit complete after {result.nfev} evaluations")
        print(f"LL: {init_ll:.2f} → {best_ll:.2f}")

    return best_p, best_ll


def print_params(params: list[float]) -> None:
    """Pretty-print fitted rule parameters."""
    print("\nFitted rule parameters:")
    for name, p in zip(PARAM_NAMES, params, strict=True):
        print(f"  {name:25s}  p={p:.6f}")


def save_result(
    params: list[float],
    ll: float,
    fit_data: FitData,
    n_realizations: int,
    n_years: int,
) -> Path:
    """Save fit results to disk."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_dir = EXPERIMENTS_DIR / f"{timestamp}_fit"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "log_likelihood": ll,
        "n_realizations": n_realizations,
        "n_years": n_years,
        "rounds": fit_data.round_numbers,
        "n_viewport_samples": sum(len(s) for s in fit_data.samples),
        "params": dict(zip(PARAM_NAMES, params, strict=True)),
    }

    path = out_dir / "fit_result.json"
    path.write_text(json.dumps(result, indent=2))
    LOGGER.info("Saved fit result to %s", path)
    return out_dir


def _parse_rounds(s: str) -> list[int]:
    """Parse '1-9' or '1,3,5' into a list of ints."""
    rounds = []
    for part in s.split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            rounds.extend(range(int(lo), int(hi) + 1))
        else:
            rounds.append(int(part))
    return rounds


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Fit rule parameters to viewport samples")
    parser.add_argument("--rounds", default="1-16", help="Rounds to fit on (e.g. 1-16)")
    parser.add_argument(
        "--n-realizations",
        type=int,
        default=1000,
        help="MC realizations (default: 1000)",
    )
    parser.add_argument("--n-years", type=int, default=50, help="Simulation steps (default: 50)")
    parser.add_argument(
        "--n-viewports",
        type=int,
        default=10,
        help="Viewports per seed (default: 10)",
    )
    parser.add_argument("--method", default="Nelder-Mead", help="Optimization method")
    parser.add_argument("--maxiter", type=int, default=300, help="Max iterations (default: 300)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument(
        "--metric",
        default="manhattan",
        choices=["manhattan", "chebyshev"],
        help="Distance metric for kernel rules (default: manhattan)",
    )
    args = parser.parse_args()

    rounds = _parse_rounds(args.rounds)

    print(f"Loading data and sampling viewports... (metric={args.metric})")
    fit_data = FitData.from_rounds(
        rounds,
        n_viewports_per_seed=args.n_viewports,
        rng_seed=args.seed,
    )

    best_p, best_ll = fit(
        fit_data,
        n_realizations=args.n_realizations,
        n_years=args.n_years,
        method=args.method,
        maxiter=args.maxiter,
        rng_seed=args.seed,
        metric=args.metric,
    )

    print_params(best_p)
    out_dir = save_result(best_p, best_ll, fit_data, args.n_realizations, args.n_years)
    print(f"\nResults saved to {out_dir}")


if __name__ == "__main__":
    main()
