"""Replay loader for Astar Island round replays.

Loads a replay JSON and provides frame-by-frame access with efficient
cell-level transition tracking.

Usage:
    from astar_island.replay import Replay

    replay = Replay.from_file("astar_island/data/round_16/replay.json")
    print(replay)

    # Step through frames
    for frame in replay:
        print(f"Step {frame.step}: {frame.n_settlements} settlements")

    # Access specific frames
    frame = replay[10]

    # Get all transitions for a cell
    for t in replay.cell_history(x=5, y=3):
        print(f"  step {t.step}: {t.old_name} -> {t.new_name}")

    # Get all cells that changed between two frames
    changes = replay.diff(0, 50)
    print(f"{len(changes)} cells changed between step 0 and step 50")

    # Get global transition summary
    replay.print_transition_summary()
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

# Raw grid value -> human-readable name (matches client.py TERRAIN_CLASSES)
TILE_NAMES: dict[int, str] = {
    11: "plains",
    10: "water",
    1: "settlement",
    2: "port",
    3: "ruin",
    4: "forest",
    5: "mountain",
}


def tile_name(value: int) -> str:
    return TILE_NAMES.get(value, f"unknown({value})")


@dataclass(frozen=True)
class Settlement:
    """Settlement snapshot at a single frame."""

    x: int
    y: int
    population: float
    food: float
    wealth: float
    defense: float
    has_port: bool
    alive: bool
    owner_id: int


@dataclass(frozen=True)
class CellTransition:
    """A single cell changing value between consecutive frames."""

    x: int
    y: int
    step: int
    old: int
    new: int

    @property
    def old_name(self) -> str:
        return tile_name(self.old)

    @property
    def new_name(self) -> str:
        return tile_name(self.new)

    def __repr__(self) -> str:
        return f"CellTransition(x={self.x}, y={self.y}, step={self.step}, {self.old_name}->{self.new_name})"


@dataclass
class Frame:
    """A single step in the replay."""

    step: int
    grid: NDArray[np.int16]  # (H, W)
    settlements: list[Settlement]

    @property
    def n_settlements(self) -> int:
        return len(self.settlements)

    @property
    def n_alive(self) -> int:
        return sum(1 for s in self.settlements if s.alive)

    def tile_at(self, x: int, y: int) -> int:
        return int(self.grid[y, x])

    def tile_name_at(self, x: int, y: int) -> str:
        return tile_name(self.tile_at(x, y))

    def settlement_at(self, x: int, y: int) -> Settlement | None:
        for s in self.settlements:
            if s.x == x and s.y == y:
                return s
        return None


class Replay:
    """Loaded replay with frame-by-frame access and transition tracking."""

    def __init__(
        self,
        round_id: str,
        seed_index: int,
        sim_seed: int,
        width: int,
        height: int,
        frames: list[Frame],
    ) -> None:
        self.round_id = round_id
        self.seed_index = seed_index
        self.sim_seed = sim_seed
        self.width = width
        self.height = height
        self.frames = frames

        # Precompute all transitions
        self._transitions: list[list[CellTransition]] = self._compute_transitions()

    @classmethod
    def from_file(cls, path: str | Path) -> Replay:
        path = Path(path)
        with path.open() as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> Replay:
        frames = []
        for raw_frame in data["frames"]:
            settlements = [
                Settlement(
                    x=s["x"],
                    y=s["y"],
                    population=s["population"],
                    food=s["food"],
                    wealth=s["wealth"],
                    defense=s["defense"],
                    has_port=s["has_port"],
                    alive=s["alive"],
                    owner_id=s["owner_id"],
                )
                for s in raw_frame["settlements"]
            ]
            frames.append(
                Frame(
                    step=raw_frame["step"],
                    grid=np.array(raw_frame["grid"], dtype=np.int16),
                    settlements=settlements,
                ),
            )
        frames.sort(key=lambda f: f.step)
        return cls(
            round_id=data["round_id"],
            seed_index=data.get("seed_index", 0),
            sim_seed=data["sim_seed"],
            width=data["width"],
            height=data["height"],
            frames=frames,
        )

    def _compute_transitions(self) -> list[list[CellTransition]]:
        """Compute per-step transitions using vectorized diffing."""
        transitions = []
        for i in range(1, len(self.frames)):
            prev = self.frames[i - 1].grid
            curr = self.frames[i].grid
            changed = prev != curr
            ys, xs = np.where(changed)
            step_transitions = [
                CellTransition(
                    x=int(x),
                    y=int(y),
                    step=self.frames[i].step,
                    old=int(prev[y, x]),
                    new=int(curr[y, x]),
                )
                for y, x in zip(ys, xs, strict=True)
            ]
            transitions.append(step_transitions)
        return transitions

    # --- Iteration ---

    def __len__(self) -> int:
        return len(self.frames)

    def __getitem__(self, index: int) -> Frame:
        return self.frames[index]

    def __iter__(self) -> Iterator[Frame]:
        return iter(self.frames)

    # --- Transitions ---

    def transitions_at_step(self, step: int) -> list[CellTransition]:
        """Get all cell transitions that occurred going INTO the given step.

        step=1 returns changes between frame 0 and frame 1.
        """
        if step < 1 or step >= len(self.frames):
            return []
        return self._transitions[step - 1]

    def diff(self, step_a: int, step_b: int) -> list[CellTransition]:
        """Get all cells that differ between two arbitrary frames."""
        fa = self.frames[step_a]
        fb = self.frames[step_b]
        changed = fa.grid != fb.grid
        ys, xs = np.where(changed)
        return [
            CellTransition(
                x=int(x),
                y=int(y),
                step=fb.step,
                old=int(fa.grid[y, x]),
                new=int(fb.grid[y, x]),
            )
            for y, x in zip(ys, xs, strict=True)
        ]

    def cell_history(self, x: int, y: int) -> list[CellTransition]:
        """Get all transitions for a specific cell across the entire replay."""
        return [t for step_ts in self._transitions for t in step_ts if t.x == x and t.y == y]

    def all_transitions(self) -> list[CellTransition]:
        """Flat list of every transition across all steps."""
        return [t for step_ts in self._transitions for t in step_ts]

    # --- Analysis ---

    def transition_counts(self) -> dict[tuple[str, str], int]:
        """Count occurrences of each (old_name, new_name) transition type."""
        counts: dict[tuple[str, str], int] = {}
        for t in self.all_transitions():
            key = (t.old_name, t.new_name)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def cells_ever_changed(self) -> NDArray[np.bool_]:
        """Return (H, W) bool mask of cells that changed at least once."""
        mask = np.zeros((self.height, self.width), dtype=bool)
        for step_ts in self._transitions:
            for t in step_ts:
                mask[t.y, t.x] = True
        return mask

    def changes_per_step(self) -> list[int]:
        """Number of cell changes at each step transition."""
        return [len(ts) for ts in self._transitions]

    def print_transition_summary(self) -> None:
        """Print a summary of all transition types."""
        counts = self.transition_counts()
        total = sum(counts.values())
        print(f"Total cell transitions: {total}")  # noqa: T201
        print(  # noqa: T201
            f"Steps with changes: {sum(1 for ts in self._transitions if ts)}/{len(self._transitions)}",
        )
        print(  # noqa: T201
            f"Cells ever changed: {self.cells_ever_changed().sum()}/{self.width * self.height}",
        )
        print()  # noqa: T201
        print("Transition types (old -> new):")  # noqa: T201
        for (old, new), count in sorted(counts.items(), key=lambda x: -x[1]):
            print(  # noqa: T201
                f"  {old:>12s} -> {new:<12s}  {count:5d}  ({100 * count / total:.1f}%)",
            )

    # --- repr ---

    def __repr__(self) -> str:
        return (
            f"Replay(round_id='{self.round_id}', "
            f"seed={self.sim_seed}, "
            f"{self.width}x{self.height}, "
            f"{len(self.frames)} frames, "
            f"{sum(len(ts) for ts in self._transitions)} total transitions)"
        )
