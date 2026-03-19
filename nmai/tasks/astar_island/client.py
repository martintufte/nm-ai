"""Astar Island API client.

Handles all communication with the Astar Island competition API.

Usage:
    client = AstarIslandClient(token="your_jwt_token")
    rounds = client.get_rounds()
    round_data = client.get_round(round_id=1)
    budget = client.get_budget()
    observation = client.simulate(round_id=1, seed_index=0, x=10, y=10)
    client.submit(round_id=1, predictions=predictions_array)
"""

import requests
import numpy as np
from numpy.typing import NDArray

BASE_URL = "https://api.ainm.no/astar-island"

MAP_SIZE = 40
VIEWPORT_SIZE = 15
NUM_SEEDS = 5
NUM_CLASSES = 6
QUERY_BUDGET = 50

# Terrain class mapping
TERRAIN_CLASSES = {
    0: "Ocean/Plains/Empty",  # Static
    1: "Settlement",          # Dynamic
    2: "Port",                # Coastal settlements
    3: "Ruin",                # Collapsed settlements
    4: "Forest",              # Reclaims abandoned land
    5: "Mountain",            # Permanent
}


class AstarIslandClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def get_rounds(self) -> dict:
        """List active rounds."""
        resp = self.session.get(f"{BASE_URL}/rounds")
        resp.raise_for_status()
        return resp.json()

    def get_round(self, round_id: int) -> dict:
        """Get round details + initial map states."""
        resp = self.session.get(f"{BASE_URL}/rounds/{round_id}")
        resp.raise_for_status()
        return resp.json()

    def get_budget(self) -> dict:
        """Get remaining query budget."""
        resp = self.session.get(f"{BASE_URL}/budget")
        resp.raise_for_status()
        return resp.json()

    def simulate(self, round_id: int, seed_index: int, x: int, y: int) -> dict:
        """Query a 15x15 viewport (costs 1 query).

        Args:
            round_id: The round to query
            seed_index: Which seed (0-4) to observe
            x: Top-left x coordinate of viewport
            y: Top-left y coordinate of viewport

        Returns:
            Grid data, settlements list, viewport bounds.
        """
        resp = self.session.post(
            f"{BASE_URL}/simulate",
            json={
                "round_id": round_id,
                "seed_index": seed_index,
                "x": x,
                "y": y,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def submit(self, round_id: int, predictions: NDArray[np.float64]) -> dict:
        """Submit predictions.

        Args:
            round_id: The round to submit for
            predictions: Shape [40][40][6] array of probabilities.
                         Each cell's 6 values must sum to ~1.0.
        """
        assert predictions.shape == (MAP_SIZE, MAP_SIZE, NUM_CLASSES)
        resp = self.session.post(
            f"{BASE_URL}/submit",
            json={
                "round_id": round_id,
                "predictions": predictions.tolist(),
            },
        )
        resp.raise_for_status()
        return resp.json()

    def get_my_rounds(self) -> dict:
        """Get team-specific round data."""
        resp = self.session.get(f"{BASE_URL}/my-rounds")
        resp.raise_for_status()
        return resp.json()

    def get_my_predictions(self, round_id: int) -> dict:
        """Get submitted predictions for a round."""
        resp = self.session.get(f"{BASE_URL}/my-predictions/{round_id}")
        resp.raise_for_status()
        return resp.json()

    def get_analysis(self, round_id: int, seed_index: int) -> dict:
        """Get post-round ground truth comparison."""
        resp = self.session.get(f"{BASE_URL}/analysis/{round_id}/{seed_index}")
        resp.raise_for_status()
        return resp.json()

    def get_leaderboard(self) -> dict:
        """Get public standings."""
        resp = self.session.get(f"{BASE_URL}/leaderboard")
        resp.raise_for_status()
        return resp.json()
