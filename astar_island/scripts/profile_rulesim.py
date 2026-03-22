"""Profile RuleSimulator to find performance bottlenecks.

Usage:
    uv run python -m astar_island.scripts.profile_rulesim
    uv run python -m astar_island.scripts.profile_rulesim --cprofile
"""

import argparse
import cProfile
import pstats
import time
from pathlib import Path

import numpy as np

from astar_island.model import create_seed_state
from astar_island.predictor.rulesim import (
    LongboatForestToRuin,
    LongboatForestToSettlement,
    LongboatPlainsToRuin,
    LongboatPlainsToSettlement,
    LongboatRuinToPort,
    LongboatSettlementToPort,
    PortToRuin,
    RuleSimPredictor,
    RuleSimulator,
    RuinToForest,
    RuinToPlains,
    RuinToSettlement,
    SettlementToRuin,
    StaticMasks,
)
from astar_island.replay import Replay


def load_grid(data_dir: str = "astar_island/data") -> tuple[np.ndarray, "StaticMasks"]:
    """Load the first available replay and return its initial grid + static masks."""
    data_path = Path(data_dir)
    paths = sorted(data_path.glob("round_*/replay*.json"))
    if not paths:
        raise FileNotFoundError(f"No replay files found in {data_dir}")
    replay = Replay.from_file(paths[0])
    print(f"Loaded {paths[0]} ({replay.width}x{replay.height}, {len(replay.frames)} frames)")
    grid = replay.frames[0].grid
    seed_state = create_seed_state(0, grid)
    static = StaticMasks.from_grid(grid, seed_state.coastal_mask)
    return grid, static


def profile_per_rule(grid: np.ndarray, static: StaticMasks) -> None:
    """Time each rule individually across the full simulation."""
    predictor = RuleSimPredictor()
    rules = predictor.rules
    sim = RuleSimulator(rules=rules, n_realizations=predictor.n_realizations, n_years=predictor.n_years)

    rng = np.random.default_rng(42)
    h, w = grid.shape
    from astar_island.predictor.rulesim import _raw_grid_to_class_grid

    class_grid = _raw_grid_to_class_grid(grid)
    grids = np.broadcast_to(class_grid, (sim.n_realizations, h, w)).copy()

    # Warm up
    for rule in rules:
        rule.apply(grids.copy(), static, np.random.default_rng(0))

    # Time each rule across all years
    rule_times: dict[str, float] = {}
    print(f"\nProfiling {len(rules)} rules, {sim.n_realizations} realizations, {sim.n_years} years")
    print(f"Grid shape: {grid.shape}, grids shape: {grids.shape}")
    print()

    # Time the full simulation
    t0 = time.perf_counter()
    sim.simulate(grid, static, rng_seed=42)
    total_time = time.perf_counter() - t0
    print(f"Full simulate(): {total_time:.3f}s\n")

    # Now time per-rule (fresh grids each time to get representative timings)
    for rule in rules:
        grids_copy = np.broadcast_to(class_grid, (sim.n_realizations, h, w)).copy()
        rng_rule = np.random.default_rng(42)
        t0 = time.perf_counter()
        for _ in range(sim.n_years):
            rule.apply(grids_copy, static, rng_rule)
        elapsed = time.perf_counter() - t0
        rule_times[rule.name] = elapsed

    total_rule_time = sum(rule_times.values())
    print(f"{'Rule':<30s}  {'Time (s)':>10s}  {'% of rules':>10s}  {'ms/step':>10s}")
    print("-" * 65)
    for name, t in sorted(rule_times.items(), key=lambda x: -x[1]):
        print(f"{name:<30s}  {t:10.3f}  {100 * t / total_rule_time:9.1f}%  {1000 * t / sim.n_years:10.2f}")
    print("-" * 65)
    print(f"{'TOTAL':<30s}  {total_rule_time:10.3f}")


def profile_cprofile(grid: np.ndarray, static: StaticMasks) -> None:
    """Run under cProfile for function-level breakdown."""
    predictor = RuleSimPredictor()
    sim = RuleSimulator(rules=predictor.rules, n_realizations=predictor.n_realizations, n_years=predictor.n_years)

    profiler = cProfile.Profile()
    profiler.enable()
    sim.simulate(grid, static, rng_seed=42)
    profiler.disable()

    print("\n=== cProfile top 30 by cumulative time ===")
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    stats.print_stats(30)

    print("\n=== cProfile top 30 by total time ===")
    stats.sort_stats("tottime")
    stats.print_stats(30)


def profile_longboat(grid: np.ndarray, static: StaticMasks) -> None:
    """Profile with Longboat (water-boosted) rules."""
    rules = [
        RuinToForest(),
        SettlementToRuin(),
        RuinToSettlement(),
        RuinToPlains(),
        PortToRuin(),
        LongboatPlainsToSettlement(),
        LongboatForestToSettlement(),
        LongboatPlainsToRuin(),
        LongboatForestToRuin(),
        LongboatSettlementToPort(),
        LongboatRuinToPort(),
    ]
    sim = RuleSimulator(rules=rules, n_realizations=1000, n_years=50)

    from astar_island.predictor.rulesim import _raw_grid_to_class_grid

    class_grid = _raw_grid_to_class_grid(grid)
    h, w = grid.shape

    print("\n=== Longboat rules profiling ===")
    print(f"Profiling {len(rules)} rules, {sim.n_realizations} realizations, {sim.n_years} years")

    # Full simulation timing
    t0 = time.perf_counter()
    sim.simulate(grid, static, rng_seed=42)
    total_time = time.perf_counter() - t0
    print(f"Full simulate(): {total_time:.3f}s\n")

    # Per-rule timing
    rule_times: dict[str, float] = {}
    for rule in rules:
        grids_copy = np.broadcast_to(class_grid, (sim.n_realizations, h, w)).copy()
        rng_rule = np.random.default_rng(42)
        t0 = time.perf_counter()
        for _ in range(sim.n_years):
            rule.apply(grids_copy, static, rng_rule)
        elapsed = time.perf_counter() - t0
        rule_times[rule.name] = elapsed

    total_rule_time = sum(rule_times.values())
    print(f"{'Rule':<50s}  {'Time (s)':>10s}  {'% of rules':>10s}  {'ms/step':>10s}")
    print("-" * 85)
    for name, t in sorted(rule_times.items(), key=lambda x: -x[1]):
        print(f"{name:<50s}  {t:10.3f}  {100 * t / total_rule_time:9.1f}%  {1000 * t / sim.n_years:10.2f}")
    print("-" * 85)
    print(f"{'TOTAL':<50s}  {total_rule_time:10.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile RuleSimulator")
    parser.add_argument("--cprofile", action="store_true", help="Run cProfile analysis")
    parser.add_argument("--longboat", action="store_true", help="Profile with Longboat rules")
    args = parser.parse_args()

    grid, static = load_grid()
    profile_per_rule(grid, static)
    if args.longboat:
        profile_longboat(grid, static)
    if args.cprofile:
        profile_cprofile(grid, static)


if __name__ == "__main__":
    main()
