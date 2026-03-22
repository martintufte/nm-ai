"""Evaluate candidate rules against replay data.

Usage:
    uv run python -m astar_island.scripts.evaluate_rules
    uv run python -m astar_island.scripts.evaluate_rules --max-dist 2
    uv run python -m astar_island.scripts.evaluate_rules --rule RuinToForest
"""

from __future__ import annotations

import argparse
import time

from astar_island.predictor.rule_candidates import generate_candidates
from astar_island.predictor.rule_eval import ReplayCorpus
from astar_island.predictor.rule_eval import evaluate_rule
from astar_island.predictor.rulesim import ForestToRuin
from astar_island.predictor.rulesim import ForestToSettlement
from astar_island.predictor.rulesim import LongboatForestToRuin
from astar_island.predictor.rulesim import LongboatForestToSettlement
from astar_island.predictor.rulesim import LongboatPlainsToRuin
from astar_island.predictor.rulesim import LongboatPlainsToSettlement
from astar_island.predictor.rulesim import LongboatRuinToPort
from astar_island.predictor.rulesim import LongboatSettlementToPort
from astar_island.predictor.rulesim import PlainsToRuin
from astar_island.predictor.rulesim import PlainsToSettlement
from astar_island.predictor.rulesim import PortToRuin
from astar_island.predictor.rulesim import RuinToForest
from astar_island.predictor.rulesim import RuinToPlains
from astar_island.predictor.rulesim import RuinToPort
from astar_island.predictor.rulesim import RuinToSettlement
from astar_island.predictor.rulesim import Rule
from astar_island.predictor.rulesim import SettlementToPort
from astar_island.predictor.rulesim import SettlementToRuin


def get_named_rules() -> dict[str, Rule]:
    return {
        "RuinToForest": RuinToForest(),
        "SettlementToRuin": SettlementToRuin(),
        "RuinToSettlement": RuinToSettlement(),
        "RuinToPlains": RuinToPlains(),
        "SettlementToPort": SettlementToPort(),
        "RuinToPort": RuinToPort(),
        "PortToRuin": PortToRuin(),
        "PlainsToSettlement": PlainsToSettlement(),
        "ForestToSettlement": ForestToSettlement(),
        "PlainsToRuin": PlainsToRuin(),
        "ForestToRuin": ForestToRuin(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate rules against replay data")
    parser.add_argument(
        "--max-dist",
        type=int,
        default=3,
        help="Max Chebyshev distance for candidates",
    )
    parser.add_argument(
        "--rule",
        type=str,
        default=None,
        help="Evaluate only a named rule (e.g. RuinToForest)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="astar_island/data",
        help="Replay data directory",
    )
    parser.add_argument(
        "--candidates",
        action="store_true",
        help="Generate and evaluate all candidates",
    )
    parser.add_argument(
        "--longboat",
        action="store_true",
        help="Evaluate longboat (water-boosted) rules",
    )
    args = parser.parse_args()

    print("Loading corpus...")
    corpus = ReplayCorpus.load(args.data_dir)
    print(f"  {corpus}\n")

    rules_to_eval: list[Rule] = []

    if args.rule:
        named = get_named_rules()
        if args.rule not in named:
            print(f"Unknown rule: {args.rule}")
            print(f"Available: {', '.join(named.keys())}")
            return
        rules_to_eval.append(named[args.rule])
    elif args.longboat:
        print("Evaluating longboat (water-boosted) rules...")
        longboat_factories = [
            LongboatPlainsToSettlement,
            LongboatForestToSettlement,
            LongboatPlainsToRuin,
            LongboatForestToRuin,
            LongboatSettlementToPort,
            LongboatRuinToPort,
        ]
        rules_to_eval.extend(
            factory(connectivity=connectivity, max_dist_water=max_dist_water)
            for factory in longboat_factories
            for connectivity in (4, 8)
            for max_dist_water in (10, 15, 20)
        )
        print(f"  {len(rules_to_eval)} longboat variants\n")
    elif args.candidates:
        print(f"Generating candidates (max_dist={args.max_dist})...")
        candidates = generate_candidates(corpus, max_dist=args.max_dist)
        print(f"  {len(candidates)} candidates\n")
        rules_to_eval.extend(candidates)
    else:
        # Default: evaluate known rules
        rules_to_eval.extend(get_named_rules().values())

    # Evaluate
    results = []
    for i, rule in enumerate(rules_to_eval):
        t0 = time.time()
        report = evaluate_rule(rule, corpus)
        elapsed = time.time() - t0
        results.append(report)

        if len(rules_to_eval) <= 20:
            print(report.summary())
            print(f"  ({elapsed:.1f}s)\n")
        elif (i + 1) % 50 == 0:
            print(f"  evaluated {i + 1}/{len(rules_to_eval)}...")

    # Summary table for large runs
    if len(results) > 20:
        print(
            f"\n{'Rule':<55s} {'n_imp':>6s} {'p_mle':>10s} {'CI_low':>10s} {'CI_high':>10s} {'n_elig':>10s} {'n_fired':>8s}",
        )
        print("-" * 120)

        with_fit = [r for r in results if r.fit is not None]
        with_fit.sort(key=lambda r: r.fit.n_fired, reverse=True)

        for r in with_fit:
            f = r.fit
            n_imp = r.feasibility.n_impossible
            imp_str = str(n_imp) if n_imp > 0 else ""
            print(
                f"{r.rule_name:<55s} {imp_str:>6s} {f.p_mle:>10.6f} {f.ci_low:>10.6f} "
                f"{f.ci_high:>10.6f} {f.n_eligible:>10d} {f.n_fired:>8d}",
            )

        no_fit = [r for r in results if r.fit is None]
        if no_fit:
            print(f"\n{len(no_fit)} rules with no fit (0 eligible cells)")
        n_imp_total = sum(1 for r in results if r.feasibility.n_impossible > 0)
        if n_imp_total:
            print(f"{n_imp_total} rules with impossible transitions (informational)")


if __name__ == "__main__":
    main()
