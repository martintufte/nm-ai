### F7: Analyze Production Logs

Triage a downloaded Cloud Run log dump to find issues and feed them into the backlog.

**Input:** A JSON file in `data/` (e.g. `downloaded-logs-*.json`) containing GCP structured log entries from the deployed `tripletex-service`. Each entry has a `textPayload` with a solve.py log line and a `timestamp`.

**Log format:** The `textPayload` lines come from solve.py's logging. Key line types:
- `POST /solve — base_url=... files=... prompt_length=...` — request received, marks start of a task
- `Task prompt:\n...` — the task text
- `Iteration N — stop_reason=..., usage=...` — agent loop iteration
- `GET/POST/PUT/DELETE <url> params=... data=...` — outgoing Tripletex API call
- `GET/POST/PUT/DELETE <url> → HTTP NNN: ...` (WARNING) — API error response
- `TASK SUMMARY | api_calls=N | errors=N | elapsed=...` — end of task, followed by call list

Logs may contain multiple tasks (separated by `POST /solve` entries). There may also be httpx/anthropic SDK lines (rate limits, retries) interleaved.

**Goal:** Read the log, reconstruct what happened per task, and identify anything worth acting on. This includes issues with the agent's behavior (unnecessary calls, wrong endpoints, bad sequences), issues with solve.py itself (bugs, missing guardrails), and infrastructure problems (token expiry, rate limits) if they affected outcomes.

```
Read log file
  → Separate into per-task sequences (split on POST /solve)
  → For each task: reconstruct the call sequence, note errors, assess efficiency
  → Identify issues worth filing
  → A12 (file each issue to unresolved-issues.md)
```
