"""Astar Island prediction pipeline.

Orchestrates the prediction workflow: initialize model from round data,
optionally query viewports, and submit predictions.

Usage:
    uv run python -m astar_island.predict --round-id ROUND_ID
"""

import argparse
import logging

import numpy as np
from numpy.typing import NDArray

from astar_island.client import AstarIslandClient
from astar_island.model import IslandModel
from astar_island.model import IslandPredictor

LOGGER = logging.getLogger(__name__)


def run_prediction_pipeline(
    client: AstarIslandClient,
    round_id: str,
    predictor: IslandPredictor,
    submit: bool = False,
) -> dict[int, NDArray[np.float64]]:
    """Full prediction pipeline for a round.

    Args:
        client: API client.
        round_id: Round UUID.
        predictor: Predictor class for creating the IslandModel.
        submit: Whether to submit predictions to the API.

    Returns:
        Dict mapping seed_index to (H, W, 6) prediction arrays.
    """
    round_data = client.get_round(round_id)
    budget_data = client.get_budget()

    LOGGER.info(
        "Round %d (%s): %dx%d map, %d seeds, status=%s, budget=%s",
        round_data.round_number,
        round_data.id[:8],
        round_data.map_height,
        round_data.map_width,
        round_data.seeds_count,
        round_data.status,
        budget_data,
    )

    # Initialize model with all seeds
    model = IslandModel.from_round_data(round_data=round_data, predictor=predictor)
    LOGGER.info("Model initialized with %d seeds", round_data.seeds_count)

    # TODO(martin): Update logic
    # Generate predictions
    predictions: dict[int, NDArray[np.float64]] = {}
    for seed_idx in range(round_data.seeds_count):
        predictions[seed_idx] = model.predict(seed_idx)

    # Submit predictions for each seed
    if submit:
        raise NotImplementedError("This should not be done - yet")
        for seed_idx, preds in predictions.items():
            result = client.submit(round_id=round_id, predictions=preds)
            LOGGER.info("Seed %d submission: %s", seed_idx, result)

    return predictions


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Astar Island prediction pipeline")
    parser.add_argument("--round-id", required=True, help="Round ID (UUID string)")
    parser.add_argument("--submit", action="store_true", help="Submit predictions")
    args = parser.parse_args()

    from astar_island.config import get_access_token  # noqa: PLC0415
    from astar_island.predictor import DiffusionPredictor  # noqa: PLC0415

    client = AstarIslandClient(token=get_access_token())
    predictor = DiffusionPredictor()
    run_prediction_pipeline(client, args.round_id, predictor=predictor, submit=args.submit)


if __name__ == "__main__":
    main()
