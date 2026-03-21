"""Verify simulation rules against replay data.

For each transition in the replay, checks which rules claim to cover it
and whether the transition is possible according to those rules.

Usage:
    uv run python -m astar_island.scripts.verify_rules
    uv run python -m astar_island.scripts.verify_rules --replay astar_island/data/round_16/replay.json
"""

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from astar_island.predictor.rulesim import Rule
from astar_island.predictor.rulesim import RuinToForest
from astar_island.replay import CellTransition
from astar_island.replay import Replay


@dataclass
class ImpossibleTransition:
    transition: CellTransition
    rule_name: str
    detail: str


def verify_rules(replay: Replay, rules: list[Rule]) -> None:
    """Check rules against all transitions in a replay."""
    all_transitions = replay.all_transitions()
    print(f"Checking {len(rules)} rule(s) against round replay ({len(all_transitions)} transitions)\n")

    # Group transitions by type
    by_type: dict[tuple[str, str], list[CellTransition]] = defaultdict(list)
    for t in all_transitions:
        by_type[(t.old_name, t.new_name)].append(t)

    covered_count = 0
    uncovered_types: list[tuple[str, str, int]] = []

    for (old_name, new_name), transitions in sorted(by_type.items(), key=lambda x: -len(x[1])):
        # Find rules that claim to cover this transition type
        covering_rules = [r for r in rules if r.describes_transition(old_name, new_name)]

        if not covering_rules:
            uncovered_types.append((old_name, new_name, len(transitions)))
            continue

        covered_count += len(transitions)
        print(f"{old_name} -> {new_name}: {len(transitions)} transitions")

        for rule in covering_rules:
            possible = []
            impossible: list[ImpossibleTransition] = []

            for t in transitions:
                # Get the grid from the frame BEFORE this transition
                # t.step is the step where the new value appears
                # We need the frame at t.step - 1 (which is index t.step - 1 if steps are 0-indexed frames)
                frame_idx = None
                for i, frame in enumerate(replay.frames):
                    if frame.step == t.step:
                        frame_idx = i
                        break

                if frame_idx is None or frame_idx == 0:
                    possible.append(t)
                    continue

                prev_grid = replay.frames[frame_idx - 1].grid

                if rule.is_possible(t.x, t.y, t.step, prev_grid):
                    possible.append(t)
                else:
                    # Compute detail for impossible transitions
                    detail = _impossible_detail(rule, t, prev_grid)
                    impossible.append(ImpossibleTransition(t, rule.name, detail))

            n_possible = len(possible)
            n_impossible = len(impossible)
            print(f"  {rule.name}: {n_possible} possible, {n_impossible} impossible")

            # Show first few impossible transitions
            for imp in impossible[:5]:
                print(f"    Impossible at step {imp.transition.step} "
                      f"(x={imp.transition.x}, y={imp.transition.y}): {imp.detail}")
            if len(impossible) > 5:
                print(f"    ... and {len(impossible) - 5} more")

        print()

    # Report uncovered transitions
    if uncovered_types:
        print("Uncovered transitions (no rule claims them):")
        for old_name, new_name, count in sorted(uncovered_types, key=lambda x: -x[2]):
            print(f"  {old_name} -> {new_name}: {count}")
        print()

    total = len(all_transitions)
    uncovered_total = sum(c for _, _, c in uncovered_types)
    print(f"Summary: {covered_count}/{total} transitions covered by rules, "
          f"{uncovered_total}/{total} uncovered")


def _impossible_detail(rule: Rule, t: CellTransition, prev_grid) -> str:
    """Generate a human-readable detail string for an impossible transition."""
    if isinstance(rule, RuinToForest):
        from astar_island.predictor.rulesim import _chebyshev_has_neighbor  # noqa: PLC0415

        # Check if cell was even a ruin
        if prev_grid[t.y, t.x] != 3:
            return f"cell was {prev_grid[t.y, t.x]}, not ruin"

        # Find nearest forest
        h, w = prev_grid.shape
        min_d = 999
        for dy in range(-h, h):
            for dx in range(-w, w):
                ny, nx = t.y + dy, t.x + dx
                if 0 <= ny < h and 0 <= nx < w and prev_grid[ny, nx] == 4:
                    d = max(abs(dx), abs(dy))
                    min_d = min(min_d, d)
        if min_d < 999:
            return f"nearest forest Chebyshev d={min_d}"
        return "no forest on map"

    return "rule says impossible"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify rules against replay data")
    parser.add_argument(
        "--replay",
        type=str,
        default="astar_island/data/round_16/replay.json",
        help="Path to replay JSON",
    )
    args = parser.parse_args()

    replay_path = Path(args.replay)
    if not replay_path.exists():
        print(f"Replay file not found: {replay_path}")
        return

    replay = Replay.from_file(replay_path)
    print(f"Loaded {replay}\n")

    rules: list[Rule] = [RuinToForest(p=0.1)]
    verify_rules(replay, rules)


if __name__ == "__main__":
    main()
