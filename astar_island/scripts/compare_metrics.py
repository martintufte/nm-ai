"""Compare chebyshev vs manhattan metrics via log-likelihood with optimization.

Usage:
    uv run python -m astar_island.scripts.compare_metrics
"""

from __future__ import annotations

import time

import numpy as np
from scipy.optimize import minimize

from astar_island.fetch_data import load_round
from astar_island.fit import PARAM_NAMES
from astar_island.fit import build_rules
from astar_island.fit import default_params
from astar_island.fit import params_to_vector
from astar_island.fit import vector_to_params
from astar_island.model import create_seed_state
from astar_island.predictor.rulesim import RuleSimulator
from astar_island.predictor.rulesim import StaticMasks


def compute_ll(
    params: list[float],
    raw_grids_list: list,
    gt_list: list,
    metric: str,
    n_realizations: int = 100,
) -> float:
    """Compute cross-entropy LL against ground truth (pre-loaded data)."""
    rules = build_rules(params, metric=metric)
    sim = RuleSimulator(rules=rules, n_realizations=n_realizations, n_years=50)

    total_ll = 0.0
    eps = 1e-12

    for raw_grids, gt in zip(raw_grids_list, gt_list, strict=True):
        for seed_idx in range(raw_grids.shape[0]):
            raw_grid = raw_grids[seed_idx]
            seed_state = create_seed_state(seed_idx, raw_grid)
            static = StaticMasks.from_grid(raw_grid, seed_state.coastal_mask)
            probs = sim.simulate(raw_grid, static, rng_seed=42)

            dynamic = (raw_grid != 10) & (raw_grid != 5)
            gt_dist = gt[seed_idx][dynamic]
            pred_dist = probs[dynamic]

            total_ll += np.sum(gt_dist * np.log(np.maximum(pred_dist, eps)))

    return total_ll


def load_data(rounds: list[int]):
    raw_grids_list = []
    gt_list = []
    for rnd in rounds:
        data = load_round(rnd)
        if "ground_truth" not in data:
            continue
        raw_grids_list.append(data["raw_grids"])
        gt_list.append(data["ground_truth"])
    return raw_grids_list, gt_list


def fit_metric(
    raw_grids_list,
    gt_list,
    metric: str,
    n_realizations: int = 100,
    maxiter: int = 80,
) -> tuple[list[float], float]:
    init_p = default_params()
    x0 = params_to_vector(init_p)

    init_ll = compute_ll(init_p, raw_grids_list, gt_list, metric, n_realizations)
    print(f"  Initial LL: {init_ll:.2f}")

    call_count = 0
    best_so_far = [init_ll]

    def objective(x):
        nonlocal call_count
        p = vector_to_params(x)
        ll = compute_ll(p, raw_grids_list, gt_list, metric, n_realizations)
        call_count += 1
        best_so_far[0] = max(best_so_far[0], ll)
        if call_count % 5 == 0:
            print(f"    eval {call_count:4d}  LL={ll:.2f}  best={best_so_far[0]:.2f}", flush=True)
        return -ll

    result = minimize(
        objective,
        x0,
        method="Nelder-Mead",
        options={"maxiter": maxiter, "xatol": 1e-4, "fatol": 0.5, "adaptive": True},
    )

    best_p = vector_to_params(result.x)
    best_ll = -result.fun
    print(f"  Final LL: {best_ll:.2f}  ({result.nfev} evals)")
    return best_p, best_ll


def main() -> None:
    n_real = 100

    # Load data once
    fit_rounds = [1, 5, 10, 15]
    all_rounds = list(range(1, 17))
    print(f"Loading fit data (rounds {fit_rounds})...")
    fit_grids, fit_gt = load_data(fit_rounds)
    print("Loading eval data (all rounds)...")
    all_grids, all_gt = load_data(all_rounds)

    n_fit_seeds = sum(g.shape[0] for g in fit_grids)
    n_all_seeds = sum(g.shape[0] for g in all_grids)
    print(f"Fit: {n_fit_seeds} seeds, Eval: {n_all_seeds} seeds, {n_real} realizations\n")

    results = {}
    for metric in ["manhattan", "chebyshev"]:
        print(f"=== {metric.upper()} ===")
        t0 = time.time()
        best_p, best_ll = fit_metric(fit_grids, fit_gt, metric, n_real, maxiter=80)
        fit_time = time.time() - t0

        # Evaluate on all rounds
        t0 = time.time()
        full_ll = compute_ll(best_p, all_grids, all_gt, metric, n_real)
        eval_time = time.time() - t0

        results[metric] = {
            "fit_ll": best_ll,
            "full_ll": full_ll,
            "params": best_p,
            "fit_time": fit_time,
            "eval_time": eval_time,
        }

        print(f"  Full eval LL: {full_ll:.2f}")
        print(f"  Time: fit={fit_time:.0f}s, eval={eval_time:.0f}s")
        for name, val in zip(PARAM_NAMES, best_p, strict=True):
            print(f"    {name:25s} = {val:.6f}")
        print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for metric, r in results.items():
        print(f"  {metric:12s}  fit_LL={r['fit_ll']:12.2f}  full_LL={r['full_ll']:12.2f}")

    m_ll = results["manhattan"]["full_ll"]
    c_ll = results["chebyshev"]["full_ll"]
    winner = "chebyshev" if c_ll > m_ll else "manhattan"
    print(f"\n  Delta (cheby - manh): {c_ll - m_ll:+.2f}")
    print(f"  Winner: {winner}")


if __name__ == "__main__":
    main()
