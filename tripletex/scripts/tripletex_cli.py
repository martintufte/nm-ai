#!/usr/bin/env python3
"""CLI wrapper around the Tripletex API for use by a Claude Code subagent.

Usage:
    python tripletex_cli.py get <endpoint> [--params '{"key":"val"}']
    python tripletex_cli.py post <endpoint> --data '{"key":"val"}'
    python tripletex_cli.py put <endpoint> --data '{"key":"val"}'
    python tripletex_cli.py delete <endpoint>
    python tripletex_cli.py read-skill <skill_name>

Env vars:
    TRIPLETEX_BASE_URL     - API base URL (e.g. https://api.tripletex.io/v2/)
    TRIPLETEX_SESSION_TOKEN - Session token for Basic Auth
    CALL_LOG_FILE          - Path to JSON file where API calls are logged
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import httpx

_HERE = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _HERE / "skills"

_AVAILABLE_SKILLS = {
    p.stem: p for p in sorted(_SKILLS_DIR.glob("*.md")) if p.name != "scoring.md"
}

MAX_RESPONSE_CHARS = 20_000
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0

_PARAM_FIXES: dict[str, dict[str, str]] = {
    "customer": {"name": "customerName"},
}


def _normalize_endpoint(endpoint: str) -> str:
    endpoint = endpoint.lstrip("/")
    endpoint = endpoint.removeprefix("v2/")
    return endpoint


def _truncate(text: str) -> str:
    if len(text) <= MAX_RESPONSE_CHARS:
        return text
    return text[:MAX_RESPONSE_CHARS] + f"\n... [truncated, {len(text)} chars total]"


def _get_client() -> httpx.Client:
    base_url = os.environ["TRIPLETEX_BASE_URL"]
    token = os.environ["TRIPLETEX_SESSION_TOKEN"]
    return httpx.Client(
        base_url=base_url,
        auth=("0", token),
        headers={"Content-Type": "application/json"},
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
    )


def _log_call(method: str, endpoint: str, status_code: int, *, params: dict | None = None, data: dict | None = None) -> None:
    log_file = os.environ.get("CALL_LOG_FILE")
    if not log_file:
        return
    entry = {
        "method": method,
        "endpoint": endpoint,
        "status_code": status_code,
        "is_error": 400 <= status_code < 500,
    }
    if params:
        entry["params"] = params
    if data:
        entry["data_summary"] = json.dumps(data, ensure_ascii=False)[:200]

    # Append-only JSONL — one JSON object per line, safe under concurrent writes
    with open(log_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _retry_request(fn, *args, **kwargs):
    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = fn(*args, **kwargs)
            resp.raise_for_status()
            return resp
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_exc = e
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                print(f"Connection error ({type(e).__name__}), retrying in {delay:.1f}s...", file=sys.stderr)
                time.sleep(delay)
            else:
                raise
    raise last_exc


def cmd_get(client: httpx.Client, endpoint: str, params: dict | None) -> None:
    path = _normalize_endpoint(endpoint)
    if params:
        fixes = _PARAM_FIXES.get(path, {})
        for wrong, correct in fixes.items():
            if wrong in params:
                print(json.dumps({"error": f"Wrong param '{wrong}' for /{path}. Use '{correct}' instead."}))
                return
    try:
        resp = _retry_request(client.get, path, params=params)
    except httpx.HTTPStatusError as e:
        _log_call("GET", path, e.response.status_code, params=params)
        print(json.dumps({"error": f"HTTP {e.response.status_code}", "body": e.response.text[:2000]}))
        return
    _log_call("GET", path, resp.status_code, params=params)
    print(_truncate(json.dumps(resp.json())))


def cmd_post(client: httpx.Client, endpoint: str, data: dict) -> None:
    path = _normalize_endpoint(endpoint)
    try:
        resp = _retry_request(client.post, path, json=data)
    except httpx.HTTPStatusError as e:
        _log_call("POST", path, e.response.status_code, data=data)
        print(json.dumps({"error": f"HTTP {e.response.status_code}", "body": e.response.text[:2000]}))
        return
    _log_call("POST", path, resp.status_code, data=data)
    print(_truncate(json.dumps(resp.json())))


def cmd_put(client: httpx.Client, endpoint: str, data: dict) -> None:
    path = _normalize_endpoint(endpoint)
    try:
        resp = _retry_request(client.put, path, json=data)
    except httpx.HTTPStatusError as e:
        _log_call("PUT", path, e.response.status_code, data=data)
        print(json.dumps({"error": f"HTTP {e.response.status_code}", "body": e.response.text[:2000]}))
        return
    _log_call("PUT", path, resp.status_code, data=data)
    print(_truncate(json.dumps(resp.json())))


def cmd_delete(client: httpx.Client, endpoint: str) -> None:
    path = _normalize_endpoint(endpoint)
    try:
        resp = _retry_request(client.delete, path)
    except httpx.HTTPStatusError as e:
        _log_call("DELETE", path, e.response.status_code)
        print(json.dumps({"error": f"HTTP {e.response.status_code}", "body": e.response.text[:2000]}))
        return
    _log_call("DELETE", path, resp.status_code)
    print(json.dumps({"status": "deleted"}))


def cmd_read_skill(skill_name: str) -> None:
    if skill_name not in _AVAILABLE_SKILLS:
        available = ", ".join(sorted(_AVAILABLE_SKILLS))
        print(json.dumps({"error": f"Unknown skill '{skill_name}'. Available: {available}"}))
        return
    _log_call("READ_SKILL", skill_name, 200)
    print(_AVAILABLE_SKILLS[skill_name].read_text())


def cmd_review_plan(plan: str) -> None:
    """Review plan using claude CLI (no API key needed)."""
    import subprocess

    optimality_skills = "\n\n".join(
        p.read_text() for p in sorted(_SKILLS_DIR.glob("_optimality*.md"))
    )
    system_prompt = f"""\
You are an API call plan reviewer. You receive a plan listing intended \
Tripletex API calls and you critique it for efficiency.

{optimality_skills}

Your ONLY job is to reduce the total number of API calls. \
Parallelization and latency are irrelevant — only the total count matters.

1. Check the plan against each technique above.
2. Flag any call that can be eliminated (merged, inlined, or removed entirely). \
For each flagged call, explain which technique applies and what the replacement is.
3. If calls can be reduced, show the revised sequence with the new total count.
4. If the plan is already at minimum call count, say "Plan is optimal" and stop.

Do NOT suggest parallelization — it doesn't reduce call count. \
Do NOT suggest speculative alternatives you aren't sure work."""

    env = {**os.environ}
    env.pop("CLAUDECODE", None)

    result = subprocess.run(
        [
            "claude", "-p", plan,
            "--system-prompt", system_prompt,
            "--no-session-persistence",
            "--model", "sonnet",
            "--dangerously-skip-permissions",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    _log_call("REVIEW_PLAN", "", 200)
    if result.returncode != 0:
        print(json.dumps({"error": f"Review failed: {result.stderr[:500]}"}))
    else:
        print(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tripletex API CLI for Claude Code subagent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_get = sub.add_parser("get")
    p_get.add_argument("endpoint")
    p_get.add_argument("--params", type=json.loads, default=None)

    p_post = sub.add_parser("post")
    p_post.add_argument("endpoint")
    p_post.add_argument("--data", type=json.loads, required=True)

    p_put = sub.add_parser("put")
    p_put.add_argument("endpoint")
    p_put.add_argument("--data", type=json.loads, required=True)

    p_delete = sub.add_parser("delete")
    p_delete.add_argument("endpoint")

    p_skill = sub.add_parser("read-skill")
    p_skill.add_argument("skill_name")

    p_review = sub.add_parser("review-plan")
    p_review.add_argument("plan", help="Your intended API calls as text")

    args = parser.parse_args()

    if args.command == "read-skill":
        cmd_read_skill(args.skill_name)
        return
    if args.command == "review-plan":
        cmd_review_plan(args.plan)
        return

    client = _get_client()
    if args.command == "get":
        cmd_get(client, args.endpoint, args.params)
    elif args.command == "post":
        cmd_post(client, args.endpoint, args.data)
    elif args.command == "put":
        cmd_put(client, args.endpoint, args.data)
    elif args.command == "delete":
        cmd_delete(client, args.endpoint)


if __name__ == "__main__":
    main()
