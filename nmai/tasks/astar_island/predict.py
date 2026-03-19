"""Astar Island prediction pipeline.

Strategy:
1. Fetch round data and initial map states
2. Use query budget strategically to observe key areas
3. Build a model of terrain dynamics
4. Predict final terrain probability distributions

Usage:
    python -m nmai.tasks.astar_island.predict --token YOUR_TOKEN --round-id 1
"""

import argparse

import numpy as np
from numpy.typing import NDArray

from nmai.tasks.astar_island.client import (
    AstarIslandClient,
    MAP_SIZE,
    NUM_CLASSES,
    NUM_SEEDS,
    QUERY_BUDGET,
    VIEWPORT_SIZE,
)


def create_uniform_prior() -> NDArray[np.float64]:
    """Create a uniform probability distribution as baseline prediction."""
    predictions = np.ones((MAP_SIZE, MAP_SIZE, NUM_CLASSES)) / NUM_CLASSES
    return predictions


def ensure_min_probability(
    predictions: NDArray[np.float64], min_prob: float = 0.01
) -> NDArray[np.float64]:
    """Ensure no probability is exactly 0.0 (critical for KL divergence scoring).

    Clips all values to at least min_prob, then renormalizes each cell to sum to 1.0.
    """
    predictions = np.clip(predictions, min_prob, None)
    # Renormalize each cell
    sums = predictions.sum(axis=-1, keepdims=True)
    predictions = predictions / sums
    return predictions


def incorporate_initial_map(
    predictions: NDArray[np.float64],
    initial_map: list[list[int]],
) -> NDArray[np.float64]:
    """Update predictions based on initial map state.

    Static terrains (ocean=0, mountain=5) can be predicted with high confidence.

    TODO: Parse the initial map format from the API and update predictions.
    """
    raise NotImplementedError("Implement initial map incorporation")


def plan_queries(
    round_data: dict,
    budget_remaining: int,
) -> list[dict]:
    """Decide which viewports to query for maximum information gain.

    Strategy ideas:
    - Cover as much area as possible with non-overlapping viewports
    - Focus on dynamic areas (settlements, ports) over static (ocean, mountain)
    - Spread queries across seeds for better statistics

    TODO: Implement query planning strategy.
    """
    raise NotImplementedError("Implement query planning strategy")


def update_predictions_from_observations(
    predictions: NDArray[np.float64],
    observations: list[dict],
) -> NDArray[np.float64]:
    """Refine predictions based on observed simulation states.

    TODO: Implement prediction update logic based on viewport observations.
    """
    raise NotImplementedError("Implement prediction updates from observations")


def run_prediction_pipeline(client: AstarIslandClient, round_id: int) -> None:
    """Full prediction pipeline for a round."""
    # 1. Get round info
    round_data = client.get_round(round_id)
    budget = client.get_budget()
    print(f"Round {round_id}: budget remaining = {budget}")

    # 2. Start with uniform prior
    predictions = create_uniform_prior()

    # 3. Incorporate initial map state
    # predictions = incorporate_initial_map(predictions, round_data["initial_maps"])

    # 4. Plan and execute queries
    # queries = plan_queries(round_data, budget["remaining"])
    # observations = []
    # for q in queries:
    #     obs = client.simulate(round_id=round_id, **q)
    #     observations.append(obs)

    # 5. Update predictions from observations
    # predictions = update_predictions_from_observations(predictions, observations)

    # 6. Ensure valid probabilities
    predictions = ensure_min_probability(predictions)

    # 7. Submit
    result = client.submit(round_id=round_id, predictions=predictions)
    print(f"Submission result: {result}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Astar Island prediction pipeline")
    parser.add_argument("--token", required=True, help="JWT auth token")
    parser.add_argument("--round-id", type=int, required=True, help="Round ID")
    args = parser.parse_args()

    client = AstarIslandClient(token=args.token)
    run_prediction_pipeline(client, args.round_id)


if __name__ == "__main__":
    main()
