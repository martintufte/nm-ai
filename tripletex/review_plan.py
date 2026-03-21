"""Plan reviewer for Tripletex API call plans.

Uses a fast LLM call to critique the agent's intended API calls
against optimality techniques.
"""

from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

_OPTIMALITY_SKILLS = "\n\n".join(
    p.read_text()
    for p in sorted(_SKILLS_DIR.glob("_optimality*.md"))
)

_REVIEW_SYSTEM_PROMPT = f"""\
You are an API call plan reviewer. You receive a plan listing intended \
Tripletex API calls and you critique it for efficiency.

{_OPTIMALITY_SKILLS}

Your ONLY job is to reduce the total number of API calls. \
Parallelization and latency are irrelevant — only the total count matters.

1. Check the plan against each technique above.
2. Flag any call that can be eliminated (merged, inlined, or removed entirely). \
For each flagged call, explain which technique applies and what the replacement is.
3. If calls can be reduced, show the revised sequence with the new total count.
4. If the plan is already at minimum call count, say "Plan is optimal" and stop.

Do NOT suggest parallelization — it doesn't reduce call count. \
Do NOT suggest speculative alternatives you aren't sure work."""

REVIEW_MODEL = "claude-sonnet-4-6"


def review_plan(plan: str) -> str:
    """Review an API call plan and return optimality feedback.

    Args:
        plan: The agent's intended API calls as free-form text.

    Returns:
        LLM critique of the plan against optimality techniques.
    """
    from anthropic import Anthropic
    client = Anthropic()
    response = client.messages.create(
        model=REVIEW_MODEL,
        max_tokens=1024,
        system=_REVIEW_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": plan}],
    )
    return response.content[0].text
