"""Compare baseline vs baseline+longboat with per-round fitting via viewport queries.

For each round:
  1. Collect 50 viewport observations (ground truth samples)
  2. Fit longboat water params (a_water, b_water) to maximize LL of those viewports
  3. Score baseline vs baseline+longboat(fitted)

Usage:
    uv run python compare_rules.py [n_realizations]
"""

import sys
import time

import numpy as np
from numpy.typing import NDArray

from astar_island.model import IslandModel, RAW_VALUE_TO_CLASS, create_seed_state
from astar_island.predictor.rulesim import (
    ForestToRuin,
    ForestToSettlement,
    LongboatForestToRuin,
    LongboatForestToSettlement,
    LongboatPlainsToRuin,
    LongboatPlainsToSettlement,
    LongboatRuinToPort,
    LongboatSettlementToPort,
    PlainsToRuin,
    PlainsToSettlement,
    PortToRuin,
    Rule,
    RuleSimPredictor,
    RuleSimulator,
    RuinToForest,
    RuinToPlains,
    RuinToPort,
    RuinToSettlement,
    SettlementToPort,
    SettlementToRuin,
    StaticMasks,
)
from astar_island.query_selector import select_queries
from astar_island.simulator import AstarIslandSimulator

N_REAL = int(sys.argv[1]) if len(sys.argv) > 1 else 500
N_SEARCH = min(N_REAL, 150)  # fewer realizations for grid search


def baseline_rules() -> list[Rule]:
    return [
        RuinToForest(), SettlementToRuin(), RuinToSettlement(), RuinToPlains(),
        SettlementToPort(), RuinToPort(), PortToRuin(),
        PlainsToSettlement(), ForestToSettlement(), PlainsToRuin(), ForestToRuin(),
    ]


def longboat_rules(a_water: float, b_water: float, connectivity: int = 8, max_dist_water: int = 15) -> list[Rule]:
    """Build longboat rules with shared water kernel params."""
    return [
        LongboatPlainsToSettlement(a_water=a_water, b_water=b_water, connectivity=connectivity, max_dist_water=max_dist_water),
        LongboatForestToSettlement(a_water=a_water, b_water=b_water, connectivity=connectivity, max_dist_water=max_dist_water),
        LongboatPlainsToRuin(a_water=a_water * 0.5, b_water=b_water, connectivity=connectivity, max_dist_water=max_dist_water),
        LongboatForestToRuin(a_water=a_water * 0.5, b_water=b_water, connectivity=connectivity, max_dist_water=max_dist_water),
        LongboatSettlementToPort(a_water=a_water * 2, b_water=b_water * 0.7, connectivity=connectivity, max_dist_water=max_dist_water),
        LongboatRuinToPort(a_water=a_water * 2, b_water=b_water * 0.7, connectivity=connectivity, max_dist_water=max_dist_water),
    ]


def collect_viewports(sim: AstarIslandSimulator, rd, model: IslandModel, n_queries: int = 50):
    """Collect viewport observations using query selector."""
    queries = select_queries(model)[:n_queries]
    viewports = []
    for seed_idx, x, y in queries:
        vp = sim.simulate(sim.round_id, seed_idx, x, y)
        viewports.append(vp)
    return viewports


def viewport_ll(
    rules: list[Rule],
    viewports,
    raw_grids: list[NDArray[np.int16]],
    seed_states,
    n_realizations: int,
    eps: float = 1e-12,
) -> float:
    """Compute log-likelihood of viewport observations under rules."""
    simulator = RuleSimulator(rules=rules, n_realizations=n_realizations, n_years=50)

    # Simulate once per seed
    probs_cache: dict[int, NDArray[np.float64]] = {}
    for vp in viewports:
        if vp.seed_index not in probs_cache:
            raw_grid = raw_grids[vp.seed_index]
            ss = seed_states[vp.seed_index]
            static = StaticMasks.from_grid(raw_grid, ss.coastal_mask)
            probs_cache[vp.seed_index] = simulator.simulate(raw_grid, static, 42)

    total_ll = 0.0
    for vp in viewports:
        probs = probs_cache[vp.seed_index]
        vx, vy = vp.viewport_x, vp.viewport_y
        vh, vw = vp.viewport_h, vp.viewport_w
        region_probs = probs[vy:vy + vh, vx:vx + vw]

        raw_region = raw_grids[vp.seed_index][vy:vy + vh, vx:vx + vw]
        dynamic = (raw_region != 10) & (raw_region != 5)

        obs_classes = np.zeros_like(vp.grid, dtype=np.int8)
        for raw_val, cls_idx in RAW_VALUE_TO_CLASS.items():
            obs_classes[vp.grid == raw_val] = cls_idx

        obs = obs_classes[dynamic]
        pred_probs = region_probs[dynamic]
        cell_probs = pred_probs[np.arange(len(obs)), obs]
        total_ll += np.sum(np.log(np.maximum(cell_probs, eps)))

    return total_ll


def fit_longboat_params(
    viewports,
    raw_grids: list[NDArray[np.int16]],
    seed_states,
) -> tuple[float, float, float]:
    """Fit a_water and b_water via grid search over viewport LL.

    Uses N_SEARCH realizations for speed.
    Returns (a_water, b_water, best_ll).
    """
    # Focused grid: small a_water + a few b_water values
    grid = [
        (0.001, 0.05), (0.001, 0.15), (0.001, 0.30),
        (0.003, 0.05), (0.003, 0.15), (0.003, 0.30),
        (0.008, 0.10), (0.008, 0.20), (0.008, 0.35),
        (0.015, 0.15), (0.015, 0.30),
    ]

    base_ll = viewport_ll(baseline_rules(), viewports, raw_grids, seed_states, N_SEARCH)
    best_a, best_b, best_ll = 0.0, 0.0, base_ll

    for a_w, b_w in grid:
        rules = baseline_rules() + longboat_rules(a_w, b_w)
        ll = viewport_ll(rules, viewports, raw_grids, seed_states, N_SEARCH)
        tag = " ***" if ll > best_ll else ""
        print(f"    a={a_w:.3f} b={b_w:.2f} LL={ll:.1f} (base={base_ll:.1f}){tag}", flush=True)
        if ll > best_ll:
            best_a, best_b, best_ll = a_w, b_w, ll

    return best_a, best_b, best_ll


def score_config(rules: list[Rule], sim, rd, n_realizations: int) -> float:
    predictor = RuleSimPredictor(rules=rules, n_realizations=n_realizations, n_years=50)
    model = IslandModel.from_round_data(rd, predictor)
    preds = {i: model.predict(i) for i in range(rd.seeds_count)}
    return sim.score_average(preds)


def main():
    rounds = list(range(1, 17))
    results = []

    for rnd in rounds:
        t_round = time.time()
        print(f"--- Round {rnd} ---", flush=True)
        sim = AstarIslandSimulator.from_round_number(rnd, queries_max=50, seed=42)
        rd = sim.get_round(sim.round_id)

        # Collect viewports for fitting
        base_model = IslandModel.from_round_data(rd, RuleSimPredictor(rules=baseline_rules(), n_realizations=100))
        viewports = collect_viewports(sim, rd, base_model, n_queries=50)

        raw_grids = [sd.grid for sd in rd.seeds]
        seed_states = [create_seed_state(i, sd.grid) for i, sd in enumerate(rd.seeds)]

        # Fit longboat params via grid search
        a_w, b_w, fitted_ll = fit_longboat_params(viewports, raw_grids, seed_states)
        print(f"  best: a_water={a_w:.4f}  b_water={b_w:.4f}", flush=True)

        # Score both configs at full realizations
        base_score = score_config(baseline_rules(), sim, rd, N_REAL)
        if a_w > 0:
            fitted_rules = baseline_rules() + longboat_rules(a_w, b_w)
            fitted_score = score_config(fitted_rules, sim, rd, N_REAL)
        else:
            fitted_score = base_score

        delta = fitted_score - base_score
        elapsed = time.time() - t_round
        print(f"  baseline={base_score:.1f}  longboat={fitted_score:.1f}  delta={delta:+.1f}  ({elapsed:.0f}s)\n", flush=True)

        results.append({
            "round": rnd, "base_score": base_score, "fitted_score": fitted_score,
            "a_water": a_w, "b_water": b_w,
        })

    # Summary
    print(f"\n{'Rnd':>3}  {'Base':>6}  {'Longboat':>8}  {'Delta':>6}  {'a_water':>8}  {'b_water':>8}")
    print("-" * 55)
    for r in results:
        delta = r["fitted_score"] - r["base_score"]
        print(f"{r['round']:>3}  {r['base_score']:>6.1f}  {r['fitted_score']:>8.1f}  {delta:>+6.1f}  {r['a_water']:>8.4f}  {r['b_water']:>8.4f}")
    base_avg = np.mean([r["base_score"] for r in results])
    fit_avg = np.mean([r["fitted_score"] for r in results])
    print(f"{'Avg':>3}  {base_avg:>6.1f}  {fit_avg:>8.1f}  {fit_avg - base_avg:>+6.1f}")


if __name__ == "__main__":
    main()
