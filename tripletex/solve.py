"""Tripletex AI Accounting Agent - FastAPI endpoint.

Deploy this as a Cloud Run service and register the URL at app.ainm.no.

Usage:
    uvicorn nmai.tasks.tripletex.solve:app --host 0.0.0.0 --port 8080
"""

import asyncio
import base64
import binascii
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Literal
from typing import cast

import anthropic
import anthropic.types.beta
import httpx
from anthropic import Anthropic
from anthropic import beta_tool
from anthropic.lib.tools import BetaFunctionTool
from anthropic.lib.tools import ToolError
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer
from pydantic import BaseModel

LOG_DIR = Path(os.environ.get("LOG_DIR", "/tmp/tripletex-logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

_log_format = "%(asctime)s %(levelname)s %(name)s — %(message)s"
_log_datefmt = "%H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=_log_format,
    datefmt=_log_datefmt,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "solve.log"),
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Tripletex AI Agent")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    body = await request.body()
    logger.error(
        "Validation error on %s %s\n  Headers: %s\n  Body (first 2000 chars): %s\n  Errors: %s",
        request.method,
        request.url,
        dict(request.headers),
        body[:2000].decode(errors="replace"),
        exc.errors(),
    )
    # exc.errors() may contain tuples/bytes that aren't JSON-serializable
    errors_str = str(exc.errors())
    return JSONResponse(
        status_code=422,
        content={"detail": errors_str},
    )


# ---------------------------------------------------------------------------
# Auth - static bearer token from environment
# ---------------------------------------------------------------------------
BEARER_TOKEN = os.environ["BEARER_TOKEN"]
_security = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_security),  # noqa: B008
) -> None:
    if credentials.credentials != BEARER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )


# ---------------------------------------------------------------------------
# Load system prompt components at module level
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_SKILLS_DIR = _HERE / "skills"

# Assemble prompt in deliberate order:
# 1. Skill index — compact table telling the agent what's available via read_skill
# 2. Task prompt — role, tools, assumptions, task categories, planning
# 3. Scoring — scoring rules and efficiency tips (last, so it sticks)
_task_prompt = (_HERE / "prompt.md").read_text()
_scoring = (_SKILLS_DIR / "scoring.md").read_text()

# Build a compact index of available skill files (excluding scoring, which stays in prompt)
_AVAILABLE_SKILLS = {
    p.stem: p for p in sorted(_SKILLS_DIR.glob("*.md")) if p.name != "scoring.md"
}

_SKILL_INDEX = """\
## Available Skill References

Call `read_skill(skill_name)` to read the full reference for an entity type. \
You MUST read the relevant skill before making POST/PUT calls. \
This tool is free and does not count toward your efficiency score.

| Skill | Covers |
|-------|--------|
| _general | API patterns: references, responses, versioning, inline creation, error translations, lookups |
| customer | Customer CRUD, address nested updates |
| department | Department CRUD (no dependencies) |
| employee | Employee + Employment, userType, department req, dateOfBirth on PUT |
| invoice | Invoice + Orders + OrderLines, payment/credit note (query params), bank account prereq |
| ledger | Ledger accounts, postings, vouchers, VAT codes, currency |
| product | Product CRUD, VAT gotcha, unique names |
| project | Project CRUD, projectManager, inline participants/activities, hourly rates |
| activity | Activity CRUD, activityType, linking to projects |
| timesheet | Timesheet entry (hours registration), allocated hours, month/week approval |
| travel | Travel expenses, costs, mileage, per diem, accommodation, rate categories |"""

_FULL_SYSTEM_PROMPT = "\n\n".join(
    [_SKILL_INDEX, _task_prompt, _scoring]
)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_ITERATIONS = 20
MAX_RESPONSE_CHARS = 20_000  # Truncate large API responses


@dataclass
class CallRecord:
    method: str
    endpoint: str
    status_code: int
    is_error: bool
    params: dict | None = None
    data_summary: str | None = None


@dataclass
class CallTracker:
    calls: list[CallRecord] = field(default_factory=list)

    def record(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        *,
        params: dict | None = None,
        data: dict | None = None,
    ) -> None:
        # Keep a short summary of POST/PUT body for the log
        data_summary = None
        if data:
            data_summary = json.dumps(data, ensure_ascii=False)[:200]

        self.calls.append(
            CallRecord(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                is_error=400 <= status_code < 500,
                params=params,
                data_summary=data_summary,
            )
        )

    @property
    def api_calls(self) -> int:
        return len(self.calls)

    @property
    def errors(self) -> int:
        return sum(1 for c in self.calls if c.is_error)

    def summary_parts(self) -> list[str]:
        parts = []
        for c in self.calls:
            s = f"{c.method} {c.endpoint} → {c.status_code}"
            if c.params:
                s += f" params={c.params}"
            if c.data_summary:
                s += f" data={c.data_summary}"
            parts.append(s)
        return parts


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class TripletexCredentials(BaseModel):
    base_url: str
    session_token: str


class SolveRequest(BaseModel):
    prompt: str
    tripletex_credentials: TripletexCredentials
    files: list[str] | None = None  # Optional base64-encoded PDFs/images


class SolveResponse(BaseModel):
    status: str
    api_calls: int | None = None
    errors: int | None = None


# ---------------------------------------------------------------------------
# Tripletex session factory
# ---------------------------------------------------------------------------
def get_tripletex_client(base_url: str, session_token: str) -> httpx.Client:
    """Create an authenticated httpx client for the Tripletex API."""
    return httpx.Client(
        base_url=base_url,
        auth=("0", session_token),
        headers={"Content-Type": "application/json"},
        timeout=httpx.Timeout(
            connect=5.0,
            read=30.0,
            write=10.0,
            pool=5.0,
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _truncate(text: str) -> str:
    """Truncate a string if it exceeds MAX_RESPONSE_CHARS."""
    if len(text) <= MAX_RESPONSE_CHARS:
        return text
    return text[:MAX_RESPONSE_CHARS] + f"\n... [truncated, {len(text)} chars total]"


def _normalize_endpoint(endpoint: str) -> str:
    """Strip leading slash and redundant /v2/ prefix from an endpoint.

    The base_url already includes /v2, so passing '/v2/customer' would
    produce '/v2/v2/customer'. This helper prevents that.
    """
    endpoint = endpoint.lstrip("/")
    endpoint = endpoint.removeprefix("v2/")
    return endpoint


_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds


def _retry_request(fn, *args, **kwargs):
    """Execute an HTTP request with retry on transient connection/timeout failures.

    Retries on connection errors and timeouts only (NOT HTTP status errors).
    Uses exponential backoff with jitter.
    """
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
                logger.warning(
                    "Connection error on attempt %d (%s), retrying in %.1fs",
                    attempt + 1, type(e).__name__, delay,
                )
                time.sleep(delay)
            else:
                raise
    raise last_exc  # unreachable, but satisfies type checkers


# ---------------------------------------------------------------------------
# Tool factory — returns @beta_tool-decorated closures bound to a session
# ---------------------------------------------------------------------------
# Known param name gotchas — the API silently ignores wrong names.
# Keys are exact endpoint paths (not prefixes) to avoid false positives.
# e.g. "customer" matches GET /customer but NOT GET /customer/category
# (customer/category legitimately uses `name` as a query param).
_PARAM_FIXES: dict[str, dict[str, str]] = {
    "customer": {"name": "customerName"},
}


def make_tools(client: httpx.Client, tracker: CallTracker) -> list[BetaFunctionTool]:
    """Create Tripletex API tools bound to the given httpx client and call tracker."""

    @beta_tool
    def tripletex_get(endpoint: str, params: dict | None = None) -> str:
        """GET request to the Tripletex API. Returns JSON response.

        Args:
            endpoint: API path, e.g. 'employee' or 'invoice'. Do NOT include /v2/ prefix.
            params: Optional query parameters as key-value pairs.
        """
        path = _normalize_endpoint(endpoint)

        if params:
            fixes = _PARAM_FIXES.get(path, {})
            for wrong, correct in fixes.items():
                if wrong in params:
                    raise ToolError(
                        f"Wrong param '{wrong}' for /{path}. Use '{correct}' instead."
                    )

        logger.info("GET %s params=%s", path, params)
        try:
            resp = _retry_request(client.get, path, params=params)
        except httpx.HTTPStatusError as e:
            tracker.record("GET", path, e.response.status_code, params=params)
            logger.warning(
                "GET %s → HTTP %s: %s",
                path,
                e.response.status_code,
                e.response.text[:2000],
            )
            raise ToolError(f"HTTP {e.response.status_code}: {e.response.text[:2000]}") from e
        tracker.record("GET", path, resp.status_code, params=params)
        return _truncate(json.dumps(resp.json()))

    @beta_tool
    def tripletex_post(endpoint: str, data: dict) -> str:
        """POST request to the Tripletex API. Returns JSON response.

        Args:
            endpoint: API path, e.g. 'employee'. Do NOT include /v2/ prefix.
            data: JSON body to send.
        """
        path = _normalize_endpoint(endpoint)
        logger.info("POST %s data=%s", path, json.dumps(data)[:500])
        try:
            resp = _retry_request(client.post, path, json=data)
        except httpx.HTTPStatusError as e:
            tracker.record("POST", path, e.response.status_code, data=data)
            logger.warning(
                "POST %s → HTTP %s: %s",
                path,
                e.response.status_code,
                e.response.text[:2000],
            )
            raise ToolError(f"HTTP {e.response.status_code}: {e.response.text[:2000]}") from e
        tracker.record("POST", path, resp.status_code, data=data)
        return _truncate(json.dumps(resp.json()))

    @beta_tool
    def tripletex_put(endpoint: str, data: dict) -> str:
        """PUT request to the Tripletex API. Returns JSON response.

        Args:
            endpoint: API path, e.g. 'employee/123'. Do NOT include /v2/ prefix.
            data: JSON body to send.
        """
        path = _normalize_endpoint(endpoint)
        logger.info("PUT %s data=%s", path, json.dumps(data)[:500])
        try:
            resp = _retry_request(client.put, path, json=data)
        except httpx.HTTPStatusError as e:
            tracker.record("PUT", path, e.response.status_code, data=data)
            logger.warning(
                "PUT %s → HTTP %s: %s",
                path,
                e.response.status_code,
                e.response.text[:2000],
            )
            raise ToolError(f"HTTP {e.response.status_code}: {e.response.text[:2000]}") from e
        tracker.record("PUT", path, resp.status_code, data=data)
        return _truncate(json.dumps(resp.json()))

    @beta_tool
    def tripletex_delete(endpoint: str) -> str:
        """DELETE request to the Tripletex API. Returns confirmation on success.

        Args:
            endpoint: API path, e.g. 'employee/123'. Do NOT include /v2/ prefix.
        """
        path = _normalize_endpoint(endpoint)
        logger.info("DELETE %s", path)
        try:
            resp = _retry_request(client.delete, path)
        except httpx.HTTPStatusError as e:
            tracker.record("DELETE", path, e.response.status_code)
            logger.warning(
                "DELETE %s → HTTP %s: %s",
                path,
                e.response.status_code,
                e.response.text[:2000],
            )
            raise ToolError(f"HTTP {e.response.status_code}: {e.response.text[:2000]}") from e
        tracker.record("DELETE", path, resp.status_code)
        return json.dumps({"status": "deleted"})

    @beta_tool
    def read_skill(skill_name: str) -> str:
        """Read a skill reference file. Call this BEFORE making POST/PUT calls.

        This tool is free — it does not count toward your efficiency score.

        Args:
            skill_name: Stem name of the skill, e.g. 'employee', 'invoice', '_general'.
        """
        if skill_name not in _AVAILABLE_SKILLS:
            available = ", ".join(sorted(_AVAILABLE_SKILLS))
            raise ToolError(
                f"Unknown skill '{skill_name}'. Available skills: {available}"
            )
        return _AVAILABLE_SKILLS[skill_name].read_text()

    return [read_skill, tripletex_get, tripletex_post, tripletex_put, tripletex_delete]


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------
def build_user_message(
    task_prompt: str,
    files: list[str] | None,
) -> list[anthropic.types.beta.BetaContentBlockParam]:
    """Build the initial user message with text and optional file attachments."""
    content: list[anthropic.types.beta.BetaContentBlockParam] = [
        {"type": "text", "text": f"## Task\n\n{task_prompt}"},
    ]

    if files:
        for file_b64 in files:
            media_type = _detect_media_type(file_b64)
            # Strip data URI prefix if present
            if "," in file_b64 and file_b64.index(",") < 100:
                file_b64 = file_b64.split(",", 1)[1]  # noqa: PLW2901

            if media_type == "application/pdf":
                content.append(
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": file_b64,
                        },
                    },
                )
            else:
                image_media_type = cast(
                    Literal["image/jpeg", "image/png", "image/gif", "image/webp"],
                    media_type,
                )
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_media_type,
                            "data": file_b64,
                        },
                    },
                )

    return content


def _detect_media_type(b64_string: str) -> str:
    """Detect media type from a base64 string, possibly with data URI prefix."""
    if b64_string.startswith("data:"):
        header = b64_string.split(",", 1)[0]
        media_type = header.split(":")[1].split(";")[0]
        return media_type

    try:
        raw = base64.b64decode(b64_string[:32], validate=False)
        if raw[:4] == b"%PDF":
            return "application/pdf"
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if raw[:2] == b"\xff\xd8":
            return "image/jpeg"
    except (ValueError, binascii.Error):
        pass

    return "image/png"  # Default fallback


# ---------------------------------------------------------------------------
# Agentic loop — SDK tool runner
# ---------------------------------------------------------------------------
def parse_and_execute_task(
    task_prompt: str,
    client: httpx.Client,
    files: list[str] | None,
) -> CallTracker:
    """Run the Claude agentic loop to solve a Tripletex task.

    Uses the SDK's beta tool runner which automatically handles:
    message accumulation, tool call dispatch, error propagation,
    and stop condition detection.

    Returns the CallTracker with recorded API calls.
    """
    tracker = CallTracker()
    anthropic_client = Anthropic()
    tools = make_tools(client, tracker)
    user_content = build_user_message(task_prompt, files)

    t0 = time.monotonic()

    runner = anthropic_client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16384,
        system=[
            {
                "type": "text",
                "text": _FULL_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        tools=tools,
        messages=[{"role": "user", "content": user_content}],
        max_iterations=MAX_ITERATIONS,
    )

    iteration = 0
    for iteration, message in enumerate(runner, 1):
        tool_names = [
            b.name for b in message.content if isinstance(b, anthropic.types.beta.BetaToolUseBlock)
        ]
        logger.info(
            "Iteration %d — stop_reason=%s tools=%s usage=%s",
            iteration,
            message.stop_reason,
            tool_names or None,
            message.usage,
        )

    elapsed = time.monotonic() - t0
    call_lines = "\n  ".join(tracker.summary_parts())
    logger.info(
        "TASK SUMMARY | api_calls=%d | errors=%d | elapsed=%.1fs\n  %s",
        tracker.api_calls,
        tracker.errors,
        elapsed,
        call_lines,
    )
    return tracker


# ---------------------------------------------------------------------------
# FastAPI endpoints
# ---------------------------------------------------------------------------
@app.post("/solve", dependencies=[Depends(verify_token)])
async def solve(request: SolveRequest) -> SolveResponse:
    """Main endpoint called by the competition platform."""
    file_count = len(request.files) if request.files else 0
    file_sizes = [len(f) for f in request.files] if request.files else []
    creds = request.tripletex_credentials
    logger.info(
        "POST /solve — base_url=%s files=%d file_sizes=%s prompt_length=%d",
        creds.base_url,
        file_count,
        file_sizes,
        len(request.prompt),
    )
    logger.info("Task prompt:\n%s", request.prompt)
    if request.files:
        for i, f in enumerate(request.files):
            media = _detect_media_type(f)
            logger.info("  File %d: %s, %d chars base64", i, media, len(f))

    client = get_tripletex_client(creds.base_url, creds.session_token)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY is not set, skipping LLM agent loop")
        return SolveResponse(status="completed")

    tracker = await asyncio.to_thread(
        parse_and_execute_task,
        task_prompt=request.prompt,
        client=client,
        files=request.files,
    )

    return SolveResponse(
        status="completed",
        api_calls=tracker.api_calls,
        errors=tracker.errors,
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
