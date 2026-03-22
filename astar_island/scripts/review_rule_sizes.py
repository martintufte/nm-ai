"""Review spatial rules with different max_dist and distance metrics.

For each spatial transition, creates KernelSpawnRule variants with different
max_dist values and chebyshev vs manhattan metrics, then evaluates each
against replay data to find the best fit.

Usage:
    uv run python -m astar_island.scripts.review_rule_sizes
"""

from __future__ import annotations

import time

from astar_island.predictor.rule_eval import ReplayCorpus
from astar_island.predictor.rule_eval import evaluate_rule
from astar_island.predictor.rulesim import KernelSpawnRule

# Spatial transitions to test: (old_raw, new_raw, source_raw, description)
SPATIAL_TRANSITIONS = [
    (3, 4, 4, "RuinToForest (near forest)"),
    (11, 1, 1, "PlainsToSettlement (near settlement)"),
    (4, 1, 1, "ForestToSettlement (near settlement)"),
    (3, 1, 1, "RuinToSettlement (near settlement)"),
    (1, 2, 10, "SettlementToPort (near water)"),
    (3, 2, 10, "RuinToPort (near water)"),
    (11, 3, 1, "PlainsToRuin (near settlement)"),
    (4, 3, 1, "ForestToRuin (near settlement)"),
]

MAX_DISTS = [1, 2, 3, 5, 7, 10, 15, 25]
METRICS = ["chebyshev", "manhattan"]


def main() -> None:
    print("Loading corpus...")
    corpus = ReplayCorpus.load("astar_island/data")
    print(f"  {corpus}\n")

    for old_raw, new_raw, source_raw, desc in SPATIAL_TRANSITIONS:
        print(f"\n{'=' * 80}")
        print(f"  {desc}")
        print(f"{'=' * 80}")
        print(
            f"{'metric':<12s} {'max_d':>5s} {'feasible':>8s} {'p_mle':>10s} "
            f"{'CI_low':>10s} {'CI_high':>10s} {'CI_width':>10s} "
            f"{'n_elig':>10s} {'n_fired':>8s} {'time':>6s}",
        )
        print("-" * 100)

        results = []

        for metric in METRICS:
            for max_dist in MAX_DISTS:
                rule = KernelSpawnRule(
                    old_raw=old_raw,
                    new_raw=new_raw,
                    source_raw=source_raw,
                    a=1.0,  # placeholder, we just want eligible/fired counts
                    b=0.0,  # flat kernel (all distances equal) for MLE comparison
                    max_dist=max_dist,
                    metric=metric,
                )

                t0 = time.time()
                report = evaluate_rule(rule, corpus)
                elapsed = time.time() - t0

                f = report.feasibility
                fit = report.fit

                if fit is not None:
                    ci_width = fit.ci_high - fit.ci_low
                    results.append(
                        (metric, max_dist, fit.p_mle, ci_width, fit.n_eligible, fit.n_fired),
                    )
                    print(
                        f"{metric:<12s} {max_dist:>5d} {'YES':>8s} {fit.p_mle:>10.6f} "
                        f"{fit.ci_low:>10.6f} {fit.ci_high:>10.6f} {ci_width:>10.6f} "
                        f"{fit.n_eligible:>10d} {fit.n_fired:>8d} {elapsed:>5.1f}s",
                    )
                else:
                    n_imp = f.n_impossible
                    results.append((metric, max_dist, None, None, f.n_eligible_cells, 0))
                    print(
                        f"{metric:<12s} {max_dist:>5d} {'NO':>8s} {'':>10s} "
                        f"{'':>10s} {'':>10s} {'':>10s} "
                        f"{f.n_eligible_cells:>10d} {'':>8s} {elapsed:>5.1f}s"
                        f"  ({n_imp} impossible)",
                    )

        # Find best: highest n_fired with tightest CI among feasible
        feasible = [
            (m, d, p, ci, ne, nf) for m, d, p, ci, ne, nf in results if p is not None and nf > 0
        ]
        if feasible:
            # Best = tightest CI (relative to p_mle), filtering for reliable (n_fired >= 10)
            reliable = [r for r in feasible if r[5] >= 10]
            if reliable:
                best = min(reliable, key=lambda r: r[3])  # tightest CI
                print(
                    f"\n  Best: metric={best[0]}, max_dist={best[1]}, p_mle={best[2]:.6f}, CI_width={best[3]:.6f}",
                )
            else:
                print("\n  No reliable fits (all n_fired < 10)")


if __name__ == "__main__":
    main()
