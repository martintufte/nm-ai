"""Sort replay JSON files from a drop folder into the correct round directories.

Usage:
    uv run python -m astar_island.sort_replays [DROP_DIR]

Reads each .json file in DROP_DIR (default: astar_island/data/replays_inbox),
extracts round_id and seed_index from the JSON, and moves it to:
    astar_island/data/round_{NN}/replay_{seed_index}_{sim_seed}.json
"""

import json
import logging
import shutil
import sys
from pathlib import Path

from astar_island.fetch_data import DATA_DIR

LOGGER = logging.getLogger(__name__)

DEFAULT_INBOX = DATA_DIR / "replay_inbox"

# Round UUID -> round number
ROUND_IDS: dict[str, int] = {
    "71451d74-be9f-471f-aacd-a41f3b68a9cd": 1,
    "76909e29-f664-4b2f-b16b-61b7507277e9": 2,
    "f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb": 3,
    "8e839974-b13b-407b-a5e7-fc749d877195": 4,
    "fd3c92ff-3178-4dc9-8d9b-acf389b3982b": 5,
    "ae78003a-4efe-425a-881a-d16a39bca0ad": 6,
    "36e581f1-73f8-453f-ab98-cbe3052b701b": 7,
    "c5cdf100-a876-4fb7-b5d8-757162c97989": 8,
    "2a341ace-0f57-4309-9b89-e59fe0f09179": 9,
    "75e625c3-60cb-4392-af3e-c86a98bde8c2": 10,
    "324fde07-1670-4202-b199-7aa92ecb40ee": 11,
    "795bfb1f-54bd-4f39-a526-9868b36f7ebd": 12,
    "7b4bda99-6165-4221-97cc-27880f5e6d95": 13,
    "d0a2c894-2162-4d49-86cf-435b9013f3b8": 14,
    "cc5442dd-bc5d-418b-911b-7eb960cb0390": 15,
    "8f664aed-8839-4c85-bed0-77a2cac7c6f5": 16,
    "3eb0c25d-28fa-48ca-b8e1-fc249e3918e9": 17,
}


def sort_replays(inbox: Path = DEFAULT_INBOX) -> list[Path]:
    """Move replay files from inbox to their correct round directories.

    Returns list of destination paths for successfully sorted files.
    """
    if not inbox.exists():
        LOGGER.info("Inbox %s does not exist, nothing to do", inbox)
        return []

    json_files = sorted(inbox.glob("*.json"))
    if not json_files:
        LOGGER.info("No JSON files in %s", inbox)
        return []

    sorted_paths = []
    for src in json_files:
        try:
            data = json.loads(src.read_text())
        except (json.JSONDecodeError, OSError) as e:
            LOGGER.warning("Skipping %s: %s", src.name, e)
            continue

        round_id = data.get("round_id")
        seed_index = data.get("seed_index")

        if round_id is None or seed_index is None:
            LOGGER.warning("Skipping %s: missing round_id or seed_index", src.name)
            continue

        sim_seed = data.get("sim_seed")
        if sim_seed is None:
            LOGGER.warning("Skipping %s: missing sim_seed", src.name)
            continue

        round_number = ROUND_IDS.get(round_id)
        if round_number is None:
            LOGGER.warning("Skipping %s: unknown round_id %s", src.name, round_id)
            continue

        dest_dir = DATA_DIR / f"round_{round_number:02d}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"replay_{seed_index}_{sim_seed}.json"

        if dest.exists():
            LOGGER.warning("Overwriting existing %s", dest)

        shutil.move(str(src), str(dest))
        LOGGER.info("%s -> %s", src.name, dest)
        sorted_paths.append(dest)

    return sorted_paths


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    inbox = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INBOX
    paths = sort_replays(inbox)
    LOGGER.info("Sorted %d replay(s)", len(paths))


if __name__ == "__main__":
    main()
