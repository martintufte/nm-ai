"""Plan reviewer for Tripletex API call plans.

Uses a fast LLM call to critique the agent's intended API calls
against optimality techniques.
"""

from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_OPTIMALITY_DIR = _SKILLS_DIR / "optimality"

VALID_DOMAINS = {"invoice", "ledger", "employee", "travel", "project"}

REVIEW_MODEL = "claude-sonnet-4-6"


def _build_system_prompt(domains: list[str] | None = None) -> str:
    """Build review system prompt with only the relevant optimality skills."""
    # Always include the general agent techniques
    parts = [(_OPTIMALITY_DIR / "_optimality_agent.md").read_text()]

    if domains:
        for d in domains:
            if d in VALID_DOMAINS:
                domain_file = _OPTIMALITY_DIR / f"_optimality_{d}.md"
                if domain_file.exists():
                    parts.append(domain_file.read_text())
    else:
        # No domain hint — load all domain skills (legacy behavior)
        for p in sorted(_OPTIMALITY_DIR.glob("*.md")):
            if p.name != "_optimality_agent.md":
                parts.append(p.read_text())

    optimality_skills = "\n\n".join(parts)

    return f"""\
You are an API call plan reviewer. You receive a plan listing intended \
Tripletex API calls and you critique it for efficiency.

{optimality_skills}

Your ONLY job is to reduce the total number of API calls. \
Parallelization and latency are irrelevant — only the total count matters.

1. Check the plan against each technique above.
2. Flag any call that can be eliminated (merged, inlined, or removed entirely). \
For each flagged call, explain which technique applies and what the replacement is.
3. If calls can be reduced, show the revised sequence.
4. If the plan is already at minimum call count, say "Plan is optimal" and stop.

Do NOT suggest parallelization — it doesn't reduce call count. \
Do NOT suggest speculative alternatives you aren't sure work."""


def review_plan(plan: str, *, domains: list[str]) -> str:
    """Review an API call plan and return optimality feedback.

    Args:
        plan: The agent's intended API calls as free-form text.
        domains: The domains involved in the task. Each one of:
                 invoice, ledger, employee, travel, project.

    Returns:
        LLM critique of the plan against optimality techniques.
    """
    from anthropic import Anthropic  # noqa: PLC0415
    from anthropic.types import TextBlock  # noqa: PLC0415

    client = Anthropic()
    response = client.messages.create(
        model=REVIEW_MODEL,
        max_tokens=1024,
        system=_build_system_prompt(domains),
        messages=[{"role": "user", "content": plan}],
    )
    block = response.content[0]
    assert isinstance(block, TextBlock), f"Expected TextBlock, got {type(block).__name__}"
    return block.text
