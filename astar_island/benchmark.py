"""Benchmark predictors across all saved rounds."""

import argparse
import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from astar_island.model import IslandModel
from astar_island.model import IslandPredictor
from astar_island.simulator import AstarIslandSimulator

LOGGER = logging.getLogger(__name__)

EXPERIMENTS_DIR = Path(__file__).parent / "experiments"


def _build_predictors(rounds: list[int]) -> dict[str, IslandPredictor]:
    """Build all predictors to benchmark."""
    from astar_island.predictor import DiffusionPredictor  # noqa: PLC0415
    from astar_island.predictor import EmptyPredictor  # noqa: PLC0415
    from astar_island.predictor import UniformPredictor  # noqa: PLC0415

    # PerfectPredictor needs GT from each round, so we use a factory
    predictors: dict[str, IslandPredictor | None] = {
        "Empty": EmptyPredictor(),
        "Uniform": UniformPredictor(),
        "Diffusion": DiffusionPredictor(),
        "Perfect": None,  # built per-round
    }
    return predictors  # type: ignore[return-value]


def benchmark_round(
    round_number: int,
    predictors: dict[str, IslandPredictor | None],
    n_queries: int = 0,
    rng_seed: int = 43,
) -> dict[str, float]:
    """Run all predictors on a single round, return avg scores."""
    from astar_island.predictor import PerfectPredictor  # noqa: PLC0415

    sim = AstarIslandSimulator.from_round_number(
        round_number, queries_max=n_queries, seed=rng_seed,
    )
    rd = sim.get_round(sim.round_id)

    scores: dict[str, float] = {}
    for name, predictor in predictors.items():
        # Build PerfectPredictor per-round with its ground truth
        if predictor is None:
            predictor = PerfectPredictor(sim.ground_truth)

        model = IslandModel.from_round_data(rd, predictor)

        # Run queries if requested
        if n_queries > 0:
            from astar_island.query_selector import select_queries  # noqa: PLC0415

            # Fresh simulator per predictor so budget resets
            pred_sim = AstarIslandSimulator.from_round_number(
                round_number, queries_max=n_queries, seed=rng_seed,
            )
            queries = select_queries(model)
            for seed_idx, x, y in queries:
                result = pred_sim.simulate(pred_sim.round_id, seed_idx, x, y)
                model.update(result)

        preds = {i: model.predict(i) for i in range(rd.seeds_count)}
        scores[name] = sim.score_average(preds)

    return scores


def run_benchmark(
    rounds: list[int],
    n_queries: int = 0,
    rng_seed: int = 42,
) -> tuple[dict[str, list[float]], dict[str, float]]:
    """Run benchmark across multiple rounds.

    Returns:
        (per_round_scores, avg_scores) where per_round_scores maps
        predictor name to list of scores, and avg_scores maps to averages.
    """
    predictors = _build_predictors(rounds)
    predictor_names = list(predictors.keys())

    per_round: dict[str, list[float]] = {name: [] for name in predictor_names}

    for rnd in rounds:
        scores = benchmark_round(rnd, predictors, n_queries, rng_seed)
        for name in predictor_names:
            per_round[name].append(scores[name])
        LOGGER.info("Round %2d: %s", rnd, "  ".join(f"{name}={scores[name]:.1f}" for name in predictor_names))

    avg_scores = {name: float(np.mean(vals)) for name, vals in per_round.items()}
    return per_round, avg_scores


def save_results(
    rounds: list[int],
    per_round: dict[str, list[float]],
    avg_scores: dict[str, float],
    n_queries: int,
) -> Path:
    """Save benchmark results and bar chart."""
    from datetime import UTC, datetime  # noqa: PLC0415

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_dir = EXPERIMENTS_DIR / f"{timestamp}_benchmark_q{n_queries}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON results
    results = {
        "rounds": rounds,
        "n_queries": n_queries,
        "per_round": {name: {str(r): s for r, s in zip(rounds, scores, strict=True)} for name, scores in per_round.items()},
        "averages": avg_scores,
    }
    (out_dir / "results.json").write_text(json.dumps(results, indent=2))

    # Bar chart
    names = list(avg_scores.keys())
    values = [avg_scores[n] for n in names]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(names, values, color=["#7a7f8a", "#d4b96a", "#2d7a2d", "#30b5c7"])
    ax.set_ylabel("Average Score")
    ax.set_title(f"Predictor Benchmark — {len(rounds)} rounds, {n_queries} queries")
    ax.set_ylim(0, 100)

    for bar, val in zip(bars, values, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1,
            f"{val:.1f}",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
        )

    fig.tight_layout()
    fig.savefig(out_dir / "benchmark.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    LOGGER.info("Benchmark saved to %s", out_dir)
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

    parser = argparse.ArgumentParser(description="Benchmark Astar Island predictors")
    parser.add_argument("--rounds", default="1-16", help="Rounds to benchmark (e.g. 1-16 or 1,3,5)")
    parser.add_argument("--queries", type=int, default=0, help="Viewport queries per round (default: 0)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    args = parser.parse_args()

    rounds = _parse_rounds(args.rounds)
    per_round, avg_scores = run_benchmark(rounds, args.queries, args.seed)

    print()
    print(f"{'Predictor':>12}  {'Avg':>6}")
    print("-" * 22)
    for name, avg in avg_scores.items():
        print(f"{name:>12}  {avg:>6.1f}")

    save_results(rounds, per_round, avg_scores, args.queries)


if __name__ == "__main__":
    main()
