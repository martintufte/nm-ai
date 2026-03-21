"""Unit tests for the Astar Island API client."""

import json

import numpy as np
import pytest
import responses
from requests.exceptions import HTTPError

from astar_island.client import BASE_URL
from astar_island.client import N_CLASSES
from astar_island.client import AstarIslandClient


@pytest.fixture
def client() -> AstarIslandClient:
    return AstarIslandClient(token="test-token")


class TestGetRounds:
    @responses.activate
    def test_returns_rounds(self, client: AstarIslandClient) -> None:
        payload = {"rounds": [{"id": "abc-123", "status": "active"}]}
        responses.get(f"{BASE_URL}/rounds", json=payload, status=200)

        result = client.get_rounds()

        assert result == payload

    @responses.activate
    def test_raises_on_401(self, client: AstarIslandClient) -> None:
        responses.get(f"{BASE_URL}/rounds", json={"error": "unauthorized"}, status=401)

        with pytest.raises(HTTPError):
            client.get_rounds()


class TestGetRound:
    @responses.activate
    def test_returns_round_details(self, client: AstarIslandClient) -> None:
        payload = {
            "id": "abc-123",
            "round_number": 1,
            "status": "active",
            "map_width": 3,
            "map_height": 1,
            "seeds_count": 1,
            "initial_states": [
                {
                    "grid": [[0, 5, 1]],
                    "settlements": [{"x": 2, "y": 0, "has_port": False, "alive": True}],
                },
            ],
        }
        responses.get(f"{BASE_URL}/rounds/abc-123", json=payload, status=200)

        result = client.get_round(round_id="abc-123")

        assert result.id == "abc-123"
        assert result.round_number == 1
        assert result.status == "active"
        assert result.map_width == 3
        assert result.map_height == 1
        assert result.seeds_count == 1
        assert len(result.seeds) == 1
        assert result.seeds[0].grid.shape == (1, 3)
        assert result.seeds[0].settlements[0].x == 2

    @responses.activate
    def test_raises_on_404(self, client: AstarIslandClient) -> None:
        responses.get(f"{BASE_URL}/rounds/bad-id", json={"error": "not found"}, status=404)

        with pytest.raises(HTTPError):
            client.get_round(round_id="bad-id")


class TestGetBudget:
    @responses.activate
    def test_returns_budget(self, client: AstarIslandClient) -> None:
        payload = {
            "round_id": "abc-123",
            "queries_used": 8,
            "queries_max": 50,
            "active": True,
        }
        responses.get(f"{BASE_URL}/budget", json=payload, status=200)

        result = client.get_budget()

        assert result.round_id == "abc-123"
        assert result.queries_used == 8
        assert result.queries_max == 50
        assert result.active is True
        assert result.queries_remaining == 42


class TestSimulate:
    @responses.activate
    def test_returns_viewport_data(self, client: AstarIslandClient) -> None:
        payload = {
            "grid": [[0] * 15 for _ in range(15)],
            "settlements": [{"x": 10, "y": 10}],
            "viewport": {"x": 5, "y": 5, "width": 15, "height": 15},
        }
        responses.post(f"{BASE_URL}/simulate", json=payload, status=200)

        result = client.simulate(round_id="abc-123", seed_index=0, x=5, y=5)

        assert result == payload

    @responses.activate
    def test_sends_correct_body(self, client: AstarIslandClient) -> None:
        responses.post(f"{BASE_URL}/simulate", json={}, status=200)

        client.simulate(round_id="abc-123", seed_index=3, x=10, y=20)

        request_body = responses.calls[0].request.body
        assert request_body is not None
        body = json.loads(request_body)
        assert body == {"round_id": "abc-123", "seed_index": 3, "x": 10, "y": 20}

    @responses.activate
    def test_raises_on_budget_exceeded(self, client: AstarIslandClient) -> None:
        responses.post(f"{BASE_URL}/simulate", json={"error": "budget exceeded"}, status=429)

        with pytest.raises(HTTPError):
            client.simulate(round_id="abc-123", seed_index=0, x=0, y=0)


class TestSubmit:
    @responses.activate
    def test_submits_predictions(self, client: AstarIslandClient) -> None:
        payload = {"score": 85.5}
        responses.post(f"{BASE_URL}/submit", json=payload, status=200)

        predictions = np.ones((40, 40, N_CLASSES)) / N_CLASSES
        result = client.submit(round_id="abc-123", predictions=predictions)

        assert result == payload

    @responses.activate
    def test_sends_correct_body(self, client: AstarIslandClient) -> None:
        responses.post(f"{BASE_URL}/submit", json={}, status=200)

        predictions = np.ones((40, 40, N_CLASSES)) / N_CLASSES
        client.submit(round_id="abc-123", predictions=predictions)

        request_body = responses.calls[0].request.body
        assert request_body is not None
        body = json.loads(request_body)
        assert body["round_id"] == "abc-123"
        assert len(body["predictions"]) == 40
        assert len(body["predictions"][0]) == 40
        assert len(body["predictions"][0][0]) == N_CLASSES

    def test_rejects_wrong_ndim(self, client: AstarIslandClient) -> None:
        bad_predictions = np.ones((40, 40))  # 2D instead of 3D

        with pytest.raises(AssertionError):
            client.submit(round_id="abc-123", predictions=bad_predictions)

    def test_rejects_wrong_classes(self, client: AstarIslandClient) -> None:
        bad_predictions = np.ones((40, 40, 3))  # 3 classes instead of 6

        with pytest.raises(AssertionError):
            client.submit(round_id="abc-123", predictions=bad_predictions)


class TestGetMyRounds:
    @responses.activate
    def test_returns_my_rounds(self, client: AstarIslandClient) -> None:
        payload = {"rounds": [{"id": "abc-123", "score": 72.0}]}
        responses.get(f"{BASE_URL}/my-rounds", json=payload, status=200)

        result = client.get_my_rounds()

        assert result == payload


class TestGetMyPredictions:
    @responses.activate
    def test_returns_predictions(self, client: AstarIslandClient) -> None:
        payload = {"predictions": [[[0.16] * 6] * 40] * 40}
        responses.get(f"{BASE_URL}/my-predictions/abc-123", json=payload, status=200)

        result = client.get_my_predictions(round_id="abc-123")

        assert result == payload


class TestGetAnalysis:
    @responses.activate
    def test_returns_analysis(self, client: AstarIslandClient) -> None:
        gt = [[[0.1] * 6] * 3] * 2  # (2, 3, 6)
        pred = [[[0.2] * 6] * 3] * 2
        payload = {
            "prediction": pred,
            "ground_truth": gt,
            "score": 90.0,
            "width": 3,
            "height": 2,
            "initial_grid": [[10, 11, 5], [1, 4, 2]],
        }
        responses.get(f"{BASE_URL}/analysis/abc-123/0", json=payload, status=200)

        result = client.get_analysis(round_id="abc-123", seed_index=0)

        assert result.score == 90.0
        assert result.width == 3
        assert result.height == 2
        assert result.ground_truth.shape == (2, 3, 6)
        assert result.prediction.shape == (2, 3, 6)
        assert result.initial_grid is not None
        assert result.initial_grid.shape == (2, 3)


class TestGetLeaderboard:
    @responses.activate
    def test_returns_leaderboard(self, client: AstarIslandClient) -> None:
        payload = {"teams": [{"name": "team1", "score": 95.0}]}
        responses.get(f"{BASE_URL}/leaderboard", json=payload, status=200)

        result = client.get_leaderboard()

        assert result == payload


class TestAuthHeader:
    @responses.activate
    def test_bearer_token_sent(self, client: AstarIslandClient) -> None:
        responses.get(f"{BASE_URL}/rounds", json={}, status=200)

        client.get_rounds()

        headers = responses.calls[0].request.headers
        assert headers is not None
        assert headers["Authorization"] == "Bearer test-token"
