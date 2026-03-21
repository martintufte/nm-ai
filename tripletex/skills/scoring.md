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

- **Don't GET before POST for the same entity.** If a task says to create a new entity, POST it directly — don't search for it first. (Looking up *other* existing entities you need as dependencies is fine.)
- **Reuse POST response IDs.** The response contains the ID. Don't GET it again.
- **Inline creation.** Nest objects (e.g. orders inside invoice) in one call.
- **Never retry failed calls.** A retry doubles your error count for no benefit.
- **List GETs return full objects.** Don't re-GET by ID after finding an entity in a list response — it already has `id`, `version`, and all fields.

### Workflow call counts (reference)
- **Invoice workflow:** 2-4 calls (customer + product + invoice + payment). Customer/product may already exist.
- **Travel workflow:** 2-6 calls (employee + travelExpense + cost/mileage/perDiem/accommodation). Employee usually exists. Costs/perDiem can be inlined on the travelExpense POST.
