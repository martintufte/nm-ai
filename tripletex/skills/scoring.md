## Scoring

Your score depends on two things: **correctness** and **efficiency**.

### Correctness

Each task is checked field-by-field. `points_earned / max_points` gives a score between 0.0 and 1.0, multiplied by the task's tier weight (Tier 1 = 1×, Tier 2 = 2×, Tier 3 = 3×). If correctness < 1.0, this is your final score — efficiency does not matter.

### Efficiency (only when correctness = 1.0)

A perfect submission unlocks an efficiency bonus that can **up to double** your tier score. Two factors:

1. **API call count** — fewer calls = higher bonus. Every Tripletex API call counts.
2. **Error count** — every 4xx response reduces score. Zero is the goal.

That's it. Wall time, iteration count, and parallel vs sequential execution do **not** affect scoring.

### How to minimize calls

- **Don't search before creating.** If a task says to create a new entity, POST directly — don't GET first.
- **Reuse POST response IDs.** The response contains the ID. Don't GET it again.
- **Inline creation.** Nest objects (e.g. orders inside invoice) in one call.
- **Never retry failed calls.** A retry doubles your error count for no benefit.
- **Don't fetch what you don't need.** Use `?fields=` to limit GET responses.
