import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def get_access_token() -> str:
    """Get the ACCESS_TOKEN from environment."""
    token = os.environ.get("ACCESS_TOKEN")
    if not token:
        msg = "ACCESS_TOKEN not found. Set it in the .env file at the project root."
        raise ValueError(msg)
    return token
