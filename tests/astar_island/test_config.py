"""Unit tests for Astar Island config."""

import pytest

from astar_island.config import get_access_token


class TestGetAccessToken:
    def test_returns_token_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACCESS_TOKEN", "my-secret-token")

        assert get_access_token() == "my-secret-token"

    def test_raises_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ACCESS_TOKEN", raising=False)

        with pytest.raises(ValueError, match="ACCESS_TOKEN not found"):
            get_access_token()

    def test_raises_when_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACCESS_TOKEN", "")

        with pytest.raises(ValueError, match="ACCESS_TOKEN not found"):
            get_access_token()
