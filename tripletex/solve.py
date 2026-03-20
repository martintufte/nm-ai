"""Tripletex AI Accounting Agent - FastAPI endpoint.

Deploy this as a Cloud Run service and register the URL at app.ainm.no.

Usage:
    uvicorn nmai.tasks.tripletex.solve:app --host 0.0.0.0 --port 8080
"""

import asyncio
import base64
import json
import logging
import os
from pathlib import Path

import anthropic
import requests
from anthropic import Anthropic
from anthropic import beta_tool
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Tripletex AI Agent")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError,
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
# Auth – static bearer token from environment
# ---------------------------------------------------------------------------
BEARER_TOKEN = os.environ["BEARER_TOKEN"]
_security = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
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
_SYSTEM_PROMPT = (_HERE / "prompt.md").read_text()
_API_REFERENCE = (_HERE / "api_reference.md").read_text()
_FULL_SYSTEM_PROMPT = f"{_SYSTEM_PROMPT}\n\n{_API_REFERENCE}"

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_ITERATIONS = 50
MAX_RESPONSE_CHARS = 20_000  # Truncate large API responses


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class SolveRequest(BaseModel):
    task_prompt: str
    session_token: str
    base_url: str
    files: list[str] | None = None  # Optional base64-encoded PDFs/images


class SolveResponse(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Tripletex session factory
# ---------------------------------------------------------------------------
def get_tripletex_session(base_url: str, session_token: str) -> requests.Session:
    """Create an authenticated requests session for the Tripletex API."""
    session = requests.Session()
    session.auth = ("0", session_token)
    session.headers.update({"Content-Type": "application/json"})
    session.base_url = base_url  # type: ignore[attr-defined]
    return session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _truncate(text: str) -> str:
    """Truncate a string if it exceeds MAX_RESPONSE_CHARS."""
    if len(text) <= MAX_RESPONSE_CHARS:
        return text
    return text[:MAX_RESPONSE_CHARS] + f"\n... [truncated, {len(text)} chars total]"


# ---------------------------------------------------------------------------
# Tool factory — returns @beta_tool-decorated closures bound to a session
# ---------------------------------------------------------------------------
def make_tools(session: requests.Session):  # noqa: ANN201
    """Create Tripletex API tools bound to the given requests session."""

    @beta_tool
    def tripletex_get(endpoint: str, params: dict | None = None) -> str:
        """GET request to the Tripletex API. Returns JSON response.

        Args:
            endpoint: API path, e.g. '/v2/employee' or '/v2/invoice?fields=id,invoiceNumber'.
            params: Optional query parameters as key-value pairs.
        """
        url = f"{session.base_url}/{endpoint.lstrip('/')}"  # type: ignore[attr-defined]
        logger.info("GET %s params=%s", url, params)
        try:
            resp = session.get(url, params=params)
            resp.raise_for_status()
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "?"
            body = e.response.text[:2000] if e.response is not None else str(e)
            logger.warning("GET %s → HTTP %s: %s", url, status_code, body)
            raise ToolError(f"HTTP {status_code}: {body}") from e
        return _truncate(json.dumps(resp.json()))

    @beta_tool
    def tripletex_post(endpoint: str, data: dict) -> str:
        """POST request to the Tripletex API. Returns JSON response.

        Args:
            endpoint: API path, e.g. '/v2/employee'.
            data: JSON body to send.
        """
        url = f"{session.base_url}/{endpoint.lstrip('/')}"  # type: ignore[attr-defined]
        logger.info("POST %s data=%s", url, json.dumps(data)[:500])
        try:
            resp = session.post(url, json=data)
            resp.raise_for_status()
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "?"
            body = e.response.text[:2000] if e.response is not None else str(e)
            logger.warning("POST %s → HTTP %s: %s", url, status_code, body)
            raise ToolError(f"HTTP {status_code}: {body}") from e
        return _truncate(json.dumps(resp.json()))

    @beta_tool
    def tripletex_put(endpoint: str, data: dict) -> str:
        """PUT request to the Tripletex API. Returns JSON response.

        Args:
            endpoint: API path, e.g. '/v2/employee/123'.
            data: JSON body to send.
        """
        url = f"{session.base_url}/{endpoint.lstrip('/')}"  # type: ignore[attr-defined]
        logger.info("PUT %s data=%s", url, json.dumps(data)[:500])
        try:
            resp = session.put(url, json=data)
            resp.raise_for_status()
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "?"
            body = e.response.text[:2000] if e.response is not None else str(e)
            logger.warning("PUT %s → HTTP %s: %s", url, status_code, body)
            raise ToolError(f"HTTP {status_code}: {body}") from e
        return _truncate(json.dumps(resp.json()))

    @beta_tool
    def tripletex_delete(endpoint: str) -> str:
        """DELETE request to the Tripletex API. Returns confirmation on success.

        Args:
            endpoint: API path, e.g. '/v2/employee/123'.
        """
        url = f"{session.base_url}/{endpoint.lstrip('/')}"  # type: ignore[attr-defined]
        logger.info("DELETE %s", url)
        try:
            resp = session.delete(url)
            resp.raise_for_status()
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "?"
            body = e.response.text[:2000] if e.response is not None else str(e)
            logger.warning("DELETE %s → HTTP %s: %s", url, status_code, body)
            raise ToolError(f"HTTP {status_code}: {body}") from e
        return json.dumps({"status": "deleted"})

    return [tripletex_get, tripletex_post, tripletex_put, tripletex_delete]


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------
def build_user_message(
    task_prompt: str, files: list[str] | None,
) -> list[anthropic.types.ContentBlockParam]:
    """Build the initial user message with text and optional file attachments."""
    content: list[anthropic.types.ContentBlockParam] = [
        {"type": "text", "text": f"## Task\n\n{task_prompt}"},
    ]

    if files:
        for file_b64 in files:
            media_type = _detect_media_type(file_b64)
            # Strip data URI prefix if present
            if "," in file_b64 and file_b64.index(",") < 100:
                file_b64 = file_b64.split(",", 1)[1]

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
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
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
    except Exception:
        pass

    return "image/png"  # Default fallback


# ---------------------------------------------------------------------------
# Agentic loop — SDK tool runner
# ---------------------------------------------------------------------------
def parse_and_execute_task(
    task_prompt: str,
    session: requests.Session,
    files: list[str] | None,
) -> None:
    """Run the Claude agentic loop to solve a Tripletex task.

    Uses the SDK's beta tool runner which automatically handles:
    message accumulation, tool call dispatch, error propagation,
    and stop condition detection.
    """
    client = Anthropic()
    tools = make_tools(session)
    user_content = build_user_message(task_prompt, files)

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16384,
        system=_FULL_SYSTEM_PROMPT,
        tools=tools,
        messages=[{"role": "user", "content": user_content}],
        max_iterations=MAX_ITERATIONS,
    )

    for iteration, message in enumerate(runner, 1):
        logger.info(
            "Iteration %d — stop_reason=%s, usage=%s",
            iteration,
            message.stop_reason,
            message.usage,
        )

    logger.info("Agent finished after %d iterations", iteration)


# ---------------------------------------------------------------------------
# FastAPI endpoints
# ---------------------------------------------------------------------------
@app.post("/solve", response_model=SolveResponse, dependencies=[Depends(verify_token)])
async def solve(request: SolveRequest) -> SolveResponse:
    """Main endpoint called by the competition platform."""
    file_count = len(request.files) if request.files else 0
    file_sizes = (
        [len(f) for f in request.files] if request.files else []
    )
    logger.info(
        "POST /solve — base_url=%s files=%d file_sizes=%s prompt_length=%d",
        request.base_url,
        file_count,
        file_sizes,
        len(request.task_prompt),
    )
    logger.info("Task prompt:\n%s", request.task_prompt)
    if request.files:
        for i, f in enumerate(request.files):
            media = _detect_media_type(f)
            logger.info("  File %d: %s, %d chars base64", i, media, len(f))

    session = get_tripletex_session(request.base_url, request.session_token)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY is not set, skipping LLM agent loop")
        return SolveResponse(status="completed")

    await asyncio.to_thread(
        parse_and_execute_task,
        task_prompt=request.task_prompt,
        session=session,
        files=request.files,
    )

    return SolveResponse(status="completed")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
