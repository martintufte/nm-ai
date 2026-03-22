"""Rule evaluation pipeline: feasibility checking and MLE probability fitting."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

import numpy as np
from scipy import stats

from astar_island.predictor.rulesim import Rule
from astar_island.replay import CellTransition
from astar_island.replay import Replay
from astar_island.replay import TILE_NAMES


@dataclass
class ReplayCorpus:
    """Collection of replays for evaluation."""

    replays: list[Replay]

    @classmethod
    def load(cls, data_dir: str | Path = "astar_island/data") -> ReplayCorpus:
        data_path = Path(data_dir)
        paths = sorted(data_path.glob("round_*/replay*.json"))
        replays = [Replay.from_file(p) for p in paths]
        return cls(replays=replays)

    def step_iter(self) -> list[tuple[Replay, int, list[CellTransition]]]:
        """Yield (replay, frame_index, transitions) for each step with transitions."""
        results = []
        for replay in self.replays:
            for i in range(1, len(replay.frames)):
                transitions = replay._transitions[i - 1]
                if transitions:
                    results.append((replay, i, transitions))
        return results

    def __repr__(self) -> str:
        n_steps = sum(len(r.frames) - 1 for r in self.replays)
        n_trans = sum(sum(len(ts) for ts in r._transitions) for r in self.replays)
        return f"ReplayCorpus({len(self.replays)} replays, {n_steps} steps, {n_trans} transitions)"


@dataclass
class ImpossibleExample:
    replay_id: str
    step: int
    x: int
    y: int
    detail: str


@dataclass
class FeasibilityResult:
    n_described: int = 0
    n_possible: int = 0
    n_impossible: int = 0
    impossible_examples: list[ImpossibleExample] = field(default_factory=list)
    n_eligible_cells: int = 0
    n_actually_fired: int = 0

    @property
    def is_feasible(self) -> bool:
        return self.n_impossible == 0

    @property
    def empirical_rate(self) -> float | None:
        if self.n_eligible_cells == 0:
            return None
        return self.n_actually_fired / self.n_eligible_cells


@dataclass
class PerReplayStats:
    replay_id: str
    n_eligible: int
    n_fired: int


@dataclass
class FitResult:
    p_mle: float
    ci_low: float
    ci_high: float
    n_eligible: int
    n_fired: int
    per_replay: list[PerReplayStats]
    reliable: bool

    def summary_line(self) -> str:
        flag = "" if self.reliable else " (unreliable: n_fired<10)"
        return (
            f"p_mle={self.p_mle:.6f}  "
            f"95%CI=[{self.ci_low:.6f}, {self.ci_high:.6f}]  "
            f"n_eligible={self.n_eligible}  n_fired={self.n_fired}{flag}"
        )


@dataclass
class RuleEvalReport:
    rule_name: str
    feasibility: FeasibilityResult
    fit: FitResult | None = None

    def summary(self) -> str:
        lines = [f"=== {self.rule_name} ==="]
        f = self.feasibility
        status = "PASS" if f.is_feasible else f"WARN ({f.n_impossible} impossible)"
        lines.append(
            f"Feasibility: {status}  "
            f"(described={f.n_described}, possible={f.n_possible}, impossible={f.n_impossible})"
        )
        if f.empirical_rate is not None:
            lines.append(
                f"  eligible_cells={f.n_eligible_cells}, fired={f.n_actually_fired}, "
                f"empirical_rate={f.empirical_rate:.6f}"
            )
        if not f.is_feasible:
            for ex in f.impossible_examples[:5]:
                lines.append(
                    f"  impossible: {ex.replay_id} step={ex.step} "
                    f"({ex.x},{ex.y}): {ex.detail}"
                )
            if len(f.impossible_examples) > 5:
                lines.append(f"  ... and {len(f.impossible_examples) - 5} more")
        if self.fit is not None:
            lines.append(f"Fit: {self.fit.summary_line()}")
        return "\n".join(lines)


def _raw_name(value: int) -> str:
    return TILE_NAMES.get(value, f"unknown({value})")


def check_feasibility(rule: Rule, corpus: ReplayCorpus) -> FeasibilityResult:
    result = FeasibilityResult()

    for replay, frame_idx, transitions in corpus.step_iter():
        prev_grid = replay.frames[frame_idx - 1].grid

        # Filter transitions this rule describes
        described = [
            t for t in transitions
            if rule.describes_transition(t.old_name, t.new_name)
        ]
        result.n_described += len(described)

        # Check possibility
        for t in described:
            if rule.is_possible(t.x, t.y, t.step, prev_grid):
                result.n_possible += 1
            else:
                result.n_impossible += 1
                if len(result.impossible_examples) < 20:
                    result.impossible_examples.append(ImpossibleExample(
                        replay_id=replay.round_id,
                        step=t.step,
                        x=t.x,
                        y=t.y,
                        detail=f"cell was {_raw_name(prev_grid[t.y, t.x])}",
                    ))

        # Eligible mask counting
        eligible = rule.eligible_mask(prev_grid)
        n_eligible = int(eligible.sum())
        result.n_eligible_cells += n_eligible

        # Count how many eligible cells actually fired
        fired_mask = np.zeros_like(eligible)
        for t in described:
            if eligible[t.y, t.x]:
                fired_mask[t.y, t.x] = True
        result.n_actually_fired += int(fired_mask.sum())

    return result


def fit_rule_probability(rule: Rule, corpus: ReplayCorpus) -> FitResult:
    total_eligible = 0
    total_fired = 0
    per_replay: list[PerReplayStats] = []

    # Accumulate per-replay
    replay_accum: dict[str, tuple[int, int]] = {}

    for replay, frame_idx, transitions in corpus.step_iter():
        prev_grid = replay.frames[frame_idx - 1].grid
        eligible = rule.eligible_mask(prev_grid)
        n_eligible = int(eligible.sum())

        described = [
            t for t in transitions
            if rule.describes_transition(t.old_name, t.new_name)
        ]
        fired_mask = np.zeros_like(eligible)
        for t in described:
            if eligible[t.y, t.x]:
                fired_mask[t.y, t.x] = True
        n_fired = int(fired_mask.sum())

        total_eligible += n_eligible
        total_fired += n_fired

        key = f"{replay.round_id}_s{replay.sim_seed}"
        prev_e, prev_f = replay_accum.get(key, (0, 0))
        replay_accum[key] = (prev_e + n_eligible, prev_f + n_fired)

    for key, (e, f) in sorted(replay_accum.items()):
        per_replay.append(PerReplayStats(replay_id=key, n_eligible=e, n_fired=f))

    p_mle = total_fired / total_eligible if total_eligible > 0 else 0.0

    # Clopper-Pearson 95% CI
    alpha = 0.05
    if total_eligible > 0 and total_fired > 0:
        ci_low = stats.beta.ppf(alpha / 2, total_fired, total_eligible - total_fired + 1)
        ci_high = stats.beta.ppf(1 - alpha / 2, total_fired + 1, total_eligible - total_fired)
    elif total_eligible > 0 and total_fired == 0:
        ci_low = 0.0
        ci_high = 1 - (alpha / 2) ** (1 / total_eligible)
    else:
        ci_low = 0.0
        ci_high = 1.0

    return FitResult(
        p_mle=p_mle,
        ci_low=ci_low,
        ci_high=ci_high,
        n_eligible=total_eligible,
        n_fired=total_fired,
        per_replay=per_replay,
        reliable=total_fired >= 10,
    )


def evaluate_rule(rule: Rule, corpus: ReplayCorpus) -> RuleEvalReport:
    feasibility = check_feasibility(rule, corpus)
    fit = fit_rule_probability(rule, corpus)
    return RuleEvalReport(rule_name=rule.name, feasibility=feasibility, fit=fit)
