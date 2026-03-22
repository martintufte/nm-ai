# Tripletex Improvement Playbook

Composable actions and flows for systematically improving the Tripletex agent. Most actions already exist — this is a navigation aid, not new tooling.

---

## Composable Actions

### Evaluation & Measurement

| ID | Action | How | Key Files |
|----|--------|-----|-----------|
| **A1** | Run evaluation suite | `uv run python tripletex/scripts/run_synthetic_tasks.py --local [--tasks 1,3,5]` | `scripts/run_synthetic_tasks.py`, results in `data/` |
| **A2** | Run verification suite | `bash tripletex/tripletex-knowledge/verify.sh` | `tripletex-knowledge/verify.sh` |
| **A14** | Update optimal/best counts | Edit `build_tasks()` in `run_synthetic_tasks.py` — update `optimal` or `best` fields | `scripts/run_synthetic_tasks.py` |

### Investigation & Discovery

| ID | Action | How | Output |
|----|--------|-----|--------|
| **A3** | Analyze suboptimal task | **Start with the `[calls]` log printed after each task** — this is the authoritative list of API calls made. Do not count calls from conversation tool_use blocks (parallel calls look like fewer turns). Then check `calls_detail` in the result JSON for `REVIEW_PLAN` entries and conversation messages for the review_plan output — was it called? did it flag the inefficiency? | Entries for `unresolved-issues.md` |
| **A4** | Search for shorter API sequence | Explore the sandbox — inline scripts, CLI, curl, whatever fits | New optimality estimate + working sequence |
| **A17** | Analyze production log | Read a downloaded Cloud Run log dump from `data/`, identify issues | Entries for `unresolved-issues.md` |
| **A12** | File unresolved issue | Add entry to `tripletex-knowledge/unresolved-issues.md` per [guidelines](unresolved-issues-guidelines.md) | Backlog item |
| **A13** | Resolve an issue | Investigate (A4), apply fix (A5-A9), remove from `unresolved-issues.md` | Closed issue |

### Knowledge Encoding

| ID | Action | What it updates | Purpose |
|----|--------|----------------|---------|
| **A5** | Add verify.sh test | `tripletex-knowledge/verify.sh` | Codify API behavior, prevent regression |
| **A6** | Update skill file | `skills/*.md` or `skills/_optimality_*.md` | Agent runtime knowledge / plan reviewer knowledge |
| **A7** | Update prompt | `prompt.md` | Agent decision-making rules |
| **A8** | Add param fix | `PARAM_FIXES` in `solve.py` + `tripletex_cli.py` | Coded guardrail (intercepts known bad params) |
| **A9** | Add endpoint note / secretly required field | `ENDPOINT_NOTES` or `SECRETLY_REQUIRED_FIELDS` in `build_api_reference.py` | Baked into generated API reference |
| **A15** | Regenerate API reference | `uv run python tripletex/scripts/build_api_reference.py` | After A9 changes |
| **A16** | Add new synthetic task | Add to `build_tasks()` in `run_synthetic_tasks.py` + `synthetic-tasks.md` | Expand evaluation coverage |

---

## Flows

### F1: Full Improvement Cycle

The top-level loop. Run after artifact changes or periodically.

```
A2 (verify.sh)  — any regressions? fix first
       |
A1 (eval suite)  — run all tasks
       |
   Triage results:
     - verification failed → correctness problem (priority 1)
     - api_calls > optimal → efficiency problem (priority 2)
     - api_calls == optimal + verified → skip
       |
   For each imperfect task → F2
       |
A1 (re-run)  — confirm fixes, check regressions
       |
A14  — update best counts if improved
```

### F2: Investigate & Fix a Single Task

```
A3 (analyze call log)
       |
   Classify problem:
     ┌─ Optimality agent not called → A7 (prompt — ensure review_plan is invoked)
     ├─ Optimality agent missed it → A6 (optimality skill — teach it the pattern)
     ├─ Agent doesn't know pattern → A6 (skill) + A6 (optimality skill)
     ├─ Agent hits API error → A9 (endpoint note) + A5 (verify test)
     ├─ Agent makes wrong decision → A7 (prompt) or A6 (skill)
     ├─ Wrong param name → A8 (param fix) or A6 (skill note)
     ├─ Optimal count is wrong → A4 (sandbox search) + A14 (update count)
     └─ Agent's sequence looks correct → suspect process issue
          (task prompt misleading, setup wrong, verify checks wrong field)
          → A12 (file to unresolved-issues.md)
       |
A2 (verify nothing broke)
       |
A1 --tasks X (re-run just this task)
```

### F3: Discover & Encode New API Behavior

When sandbox exploration reveals something undocumented.

```
A4 (reproduce with CLI)
  → A5 (verify.sh test — canonical proof)
  → A9 (endpoint note if applicable) → A15 (regen reference)
  → A6 (update skill for agent)
```

### F4: Add a New Task Pattern

```
A4 (find best-known sequence in sandbox, establish optimality estimate)
  → A16 (add to run_synthetic_tasks.py + synthetic-tasks.md)
  → A1 --tasks X (run the new task)
  → If suboptimal → F2
```

### F5: Close the Gap on a Specific Task

Focused sprint: get one task from current `best` down to `optimal`.

```
A1 --tasks X (run task, capture call log)
  → A3 (map every call: necessary / avoidable / error)
  → For each avoidable call → apply fix per F2
  → A4 (if optimal seems wrong, search for better sequence to revise estimate)
  → A14 (update optimal or best)
  → Repeat until best == optimal
```

### F6: Regression Check

After any artifact change.

```
A2 (verify.sh) → A1 (full eval) → compare vs previous results → revert/fix if worse
```

### F7: Analyze Production Logs

→ [production-log-analysis.md](production-log-analysis.md)

---

## Artifact Dependency Map

```
prompt.md ─────────────┐
skills/*.md ───────────┤
scoring.md ────────────┼──► Agent system prompt (solve.py)
                       │
_optimality_*.md ──────┼──► Plan reviewer (review_plan.py)
                       │
PARAM_FIXES ───────────┼──► Coded guardrails (solve.py, tripletex_cli.py)
                       │
ENDPOINT_NOTES ────────┤
SECRETLY_REQUIRED ─────┼──► build_api_reference.py ──► api_reference.md
                       │
verify.sh ─────────────┼──► Regression gate (codified API truth)
                       │
synthetic-tasks.md ────┤
run_synthetic_tasks.py ┼──► Evaluation suite (measures progress)
                       │
unresolved-issues.md ──┼──► Backlog (drives improvement)
```

## Triage Priority

After evaluation, fix in this order:
1. **Verification failures** — wrong answer scores 0 regardless of efficiency
2. **api_calls > optimal** — biggest gap first
3. **At optimal** — no action needed

---

## Sandbox Usage

→ [sandbox-usage.md](sandbox-usage.md)
