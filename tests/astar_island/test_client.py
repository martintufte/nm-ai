"""Unit tests for the Astar Island API client."""

import json

import numpy as np
import pytest
import responses
from requests.exceptions import HTTPError

from astar_island.client import BASE_URL
from astar_island.client import MAP_SIZE
from astar_island.client import NUM_CLASSES
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
        payload = {"id": "abc-123", "initial_states": [{"grid": [[0, 5, 1]]}]}
        responses.get(f"{BASE_URL}/rounds/abc-123", json=payload, status=200)

        result = client.get_round(round_id="abc-123")

        assert result == payload

    @responses.activate
    def test_raises_on_404(self, client: AstarIslandClient) -> None:
        responses.get(f"{BASE_URL}/rounds/bad-id", json={"error": "not found"}, status=404)

        with pytest.raises(HTTPError):
            client.get_round(round_id="bad-id")


class TestGetBudget:
    @responses.activate
    def test_returns_budget(self, client: AstarIslandClient) -> None:
        payload = {"remaining": 42}
        responses.get(f"{BASE_URL}/budget", json=payload, status=200)

        result = client.get_budget()

        assert result == payload


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

        predictions = np.ones((MAP_SIZE, MAP_SIZE, NUM_CLASSES)) / NUM_CLASSES
        result = client.submit(round_id="abc-123", predictions=predictions)

        assert result == payload

    @responses.activate
    def test_sends_correct_body(self, client: AstarIslandClient) -> None:
        responses.post(f"{BASE_URL}/submit", json={}, status=200)

        predictions = np.ones((MAP_SIZE, MAP_SIZE, NUM_CLASSES)) / NUM_CLASSES
        client.submit(round_id="abc-123", predictions=predictions)

        request_body = responses.calls[0].request.body
        assert request_body is not None
        body = json.loads(request_body)
        assert body["round_id"] == "abc-123"
        assert len(body["predictions"]) == MAP_SIZE
        assert len(body["predictions"][0]) == MAP_SIZE
        assert len(body["predictions"][0][0]) == NUM_CLASSES

    def test_rejects_wrong_shape(self, client: AstarIslandClient) -> None:
        bad_predictions = np.ones((10, 10, 6))

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
        payload = {"ground_truth": [[0] * 40] * 40, "score": 90.0}
        responses.get(f"{BASE_URL}/analysis/abc-123/0", json=payload, status=200)

        result = client.get_analysis(round_id="abc-123", seed_index=0)

        assert result == payload


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
