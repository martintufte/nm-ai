"""Astar Island API client."""

from dataclasses import dataclass
from typing import Final

import numpy as np
import requests
from numpy.typing import NDArray

BASE_URL: Final[str] = "https://api.ainm.no/astar-island"
N_CLASSES: Final[int] = 6
TERRAIN_CLASSES: Final[dict[int, str]] = {
    0: "Ocean/Plains/Empty",  # Static
    1: "Settlement",  # Dynamic
    2: "Port",  # Coastal settlements
    3: "Ruin",  # Collapsed settlements
    4: "Forest",  # Reclaims abandoned land
    5: "Mountain",  # Permanent
}


@dataclass
class Settlement:
    """A settlement on the map."""

    x: int
    y: int
    has_port: bool
    alive: bool


@dataclass
class SeedData:
    """Initial state for a single seed."""

    grid: NDArray[np.int16]  # (H, W) raw grid values
    settlements: list[Settlement]


@dataclass
class BudgetData:
    """Parsed response from the get_budget API endpoint."""

    round_id: str
    queries_used: int
    queries_max: int
    active: bool

    @property
    def queries_remaining(self) -> int:
        return self.queries_max - self.queries_used


@dataclass
class RoundData:
    """Parsed response from the get_round API endpoint."""

    id: str
    round_number: int
    status: str
    map_width: int
    map_height: int
    seeds_count: int
    seeds: list[SeedData]

    @classmethod
    def from_api(cls, data: dict) -> "RoundData":
        """Parse the raw API JSON response into a RoundData."""
        seeds = []
        for state in data["initial_states"]:
            grid = np.array(state["grid"], dtype=np.int16)
            settlements = [
                Settlement(
                    x=s["x"],
                    y=s["y"],
                    has_port=s["has_port"],
                    alive=s["alive"],
                )
                for s in state["settlements"]
            ]
            seeds.append(SeedData(grid=grid, settlements=settlements))

        return cls(
            id=data["id"],
            round_number=data["round_number"],
            status=data["status"],
            map_width=data["map_width"],
            map_height=data["map_height"],
            seeds_count=data["seeds_count"],
            seeds=seeds,
        )


@dataclass
class ViewPortData:
    """Parsed response from the simulate API endpoint."""

    round_id: str
    seed_index: int
    viewport_x: int
    viewport_y: int
    viewport_w: int
    viewport_h: int
    grid: NDArray[np.int16]

    @classmethod
    def from_api(cls, data: dict, round_id: str, seed_index: int) -> "ViewPortData":
        """Parse the raw API JSON response into ViewPortData."""
        grid = np.array(data["grid"], dtype=np.int16)
        h, w = grid.shape
        return cls(
            round_id=round_id,
            seed_index=seed_index,
            viewport_x=data["x"],
            viewport_y=data["y"],
            viewport_w=w,
            viewport_h=h,
            grid=grid,
        )


@dataclass
class AnalysisData:
    """Parsed response from the get_analysis API endpoint."""

    prediction: NDArray[np.float64]  # (H, W, 6)
    ground_truth: NDArray[np.float64]  # (H, W, 6)
    score: float | None
    width: int
    height: int
    initial_grid: NDArray[np.int16] | None

    @classmethod
    def from_api(cls, data: dict) -> "AnalysisData":
        """Parse the raw API JSON response into AnalysisData."""
        initial_grid = None
        if data.get("initial_grid") is not None:
            initial_grid = np.array(data["initial_grid"], dtype=np.int16)

        return cls(
            prediction=np.array(data["prediction"], dtype=np.float64),
            ground_truth=np.array(data["ground_truth"], dtype=np.float64),
            score=data.get("score"),
            width=data["width"],
            height=data["height"],
            initial_grid=initial_grid,
        )


class AstarIslandClient:
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def get_rounds(self) -> dict:
        """List active rounds."""
        resp = self.session.get(f"{BASE_URL}/rounds")
        resp.raise_for_status()
        return resp.json()

    def get_round(self, round_id: str) -> RoundData:
        """Get round details + initial map states."""
        resp = self.session.get(f"{BASE_URL}/rounds/{round_id}")
        resp.raise_for_status()
        return RoundData.from_api(resp.json())

    def get_budget(self) -> BudgetData:
        """Get remaining query budget."""
        resp = self.session.get(f"{BASE_URL}/budget")
        resp.raise_for_status()
        data = resp.json()
        return BudgetData(
            round_id=data["round_id"],
            queries_used=data["queries_used"],
            queries_max=data["queries_max"],
            active=data["active"],
        )

    def simulate(self, round_id: str, seed_index: int, x: int, y: int) -> ViewPortData:
        """Query a 15x15 viewport (costs 1 query).

        Args:
            round_id: The round to query
            seed_index: Which seed to observe
            x: Top-left x coordinate of viewport
            y: Top-left y coordinate of viewport

        Returns:
            ViewPortData with grid and viewport bounds.
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
        return ViewPortData.from_api(resp.json(), round_id, seed_index)

    def submit(self, round_id: str, predictions: NDArray[np.float64]) -> dict:
        """Submit predictions.

        Args:
            round_id: The round to submit for
            predictions: Shape (H, W, 6) array of probabilities.
                Each cell's 6 values must sum to ~1.0.
        """
        assert predictions.ndim == 3
        assert predictions.shape[2] == N_CLASSES

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

    def get_my_predictions(self, round_id: str) -> dict:
        """Get submitted predictions for a round."""
        resp = self.session.get(f"{BASE_URL}/my-predictions/{round_id}")
        resp.raise_for_status()
        return resp.json()

    def get_analysis(self, round_id: str, seed_index: int) -> AnalysisData:
        """Get post-round ground truth comparison."""
        resp = self.session.get(f"{BASE_URL}/analysis/{round_id}/{seed_index}")
        resp.raise_for_status()
        return AnalysisData.from_api(resp.json())

    def get_leaderboard(self) -> dict:
        """Get public standings."""
        resp = self.session.get(f"{BASE_URL}/leaderboard")
        resp.raise_for_status()
        return resp.json()
