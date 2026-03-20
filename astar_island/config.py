"""Configuration for Astar Island, loaded from .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def get_access_token() -> str:
    """Get the ACCESS_TOKEN from environment."""
    token = os.environ.get("ACCESS_TOKEN")
    if not token:
        msg = "ACCESS_TOKEN not found. Set it in the .env file at the project root."
        raise ValueError(msg)
    return token
