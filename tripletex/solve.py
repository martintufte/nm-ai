"""Tripletex AI Accounting Agent - FastAPI endpoint.

Deploy this as a Cloud Run service and register the URL at app.ainm.no.

Usage:
    uvicorn nmai.tasks.tripletex.solve:app --host 0.0.0.0 --port 8080
"""

import base64
import json
import logging
import os
from pathlib import Path

import anthropic
import requests
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Tripletex AI Agent")

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
# Tool definitions for Claude
# ---------------------------------------------------------------------------
TOOLS: list[anthropic.types.ToolParam] = [
    {
        "name": "tripletex_get",
        "description": "GET request to the Tripletex API. Returns parsed JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "endpoint": {
                    "type": "string",
                    "description": "API path, e.g. '/v2/employee' or '/v2/invoice?fields=id,invoiceNumber'",
                },
                "params": {
                    "type": "object",
                    "description": "Optional query parameters as key-value pairs.",
                    "additionalProperties": True,
                },
            },
            "required": ["endpoint"],
        },
    },
    {
        "name": "tripletex_post",
        "description": "POST request to the Tripletex API. Returns parsed JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "endpoint": {
                    "type": "string",
                    "description": "API path, e.g. '/v2/employee'",
                },
                "data": {
                    "type": "object",
                    "description": "JSON body to send.",
                    "additionalProperties": True,
                },
            },
            "required": ["endpoint", "data"],
        },
    },
    {
        "name": "tripletex_put",
        "description": "PUT request to the Tripletex API. Returns parsed JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "endpoint": {
                    "type": "string",
                    "description": "API path, e.g. '/v2/employee/123'",
                },
                "data": {
                    "type": "object",
                    "description": "JSON body to send.",
                    "additionalProperties": True,
                },
            },
            "required": ["endpoint", "data"],
        },
    },
    {
        "name": "tripletex_delete",
        "description": "DELETE request to the Tripletex API. Returns nothing on success.",
        "input_schema": {
            "type": "object",
            "properties": {
                "endpoint": {
                    "type": "string",
                    "description": "API path, e.g. '/v2/employee/123'",
                },
            },
            "required": ["endpoint"],
        },
    },
]


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
# Tripletex HTTP helpers
# ---------------------------------------------------------------------------
def get_tripletex_session(base_url: str, session_token: str) -> requests.Session:
    """Create an authenticated requests session for the Tripletex API."""
    session = requests.Session()
    session.auth = ("0", session_token)
    session.headers.update({"Content-Type": "application/json"})
    # Store base_url on the session for convenience
    session.base_url = base_url  # type: ignore[attr-defined]
    return session


def tripletex_get(
    session: requests.Session,
    endpoint: str,
    params: dict | None = None,
) -> dict:
    """GET request to Tripletex API."""
    url = f"{session.base_url}/{endpoint.lstrip('/')}"  # type: ignore[attr-defined]
    response = session.get(url, params=params)
    response.raise_for_status()
    return response.json()


def tripletex_post(session: requests.Session, endpoint: str, data: dict) -> dict:
    """POST request to Tripletex API."""
    url = f"{session.base_url}/{endpoint.lstrip('/')}"  # type: ignore[attr-defined]
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()


def tripletex_put(session: requests.Session, endpoint: str, data: dict) -> dict:
    """PUT request to Tripletex API."""
    url = f"{session.base_url}/{endpoint.lstrip('/')}"  # type: ignore[attr-defined]
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()


def tripletex_delete(session: requests.Session, endpoint: str) -> None:
    """DELETE request to Tripletex API."""
    url = f"{session.base_url}/{endpoint.lstrip('/')}"  # type: ignore[attr-defined]
    response = session.delete(url)
    response.raise_for_status()


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------
def execute_tool(
    name: str, input_data: dict, session: requests.Session
) -> str:
    """Dispatch a tool call to the appropriate Tripletex helper.

    Returns a JSON string with the result or error details.
    Errors are caught so Claude sees them without crashing the loop.
    """
    try:
        if name == "tripletex_get":
            result = tripletex_get(
                session, input_data["endpoint"], input_data.get("params")
            )
            return _truncate(json.dumps(result))
        elif name == "tripletex_post":
            result = tripletex_post(
                session, input_data["endpoint"], input_data["data"]
            )
            return _truncate(json.dumps(result))
        elif name == "tripletex_put":
            result = tripletex_put(
                session, input_data["endpoint"], input_data["data"]
            )
            return _truncate(json.dumps(result))
        elif name == "tripletex_delete":
            tripletex_delete(session, input_data["endpoint"])
            return json.dumps({"status": "deleted"})
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        body = ""
        if e.response is not None:
            try:
                body = e.response.text[:2000]
            except Exception:
                body = str(e)
        logger.warning("Tool %s returned HTTP %s: %s", name, status, body)
        return json.dumps({"error": f"HTTP {status}", "details": body})


def _truncate(text: str) -> str:
    """Truncate a string if it exceeds MAX_RESPONSE_CHARS."""
    if len(text) <= MAX_RESPONSE_CHARS:
        return text
    return text[:MAX_RESPONSE_CHARS] + f"\n... [truncated, {len(text)} chars total]"


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------
def build_user_message(
    task_prompt: str, files: list[str] | None
) -> list[anthropic.types.ContentBlockParam]:
    """Build the initial user message with text and optional file attachments."""
    content: list[anthropic.types.ContentBlockParam] = [
        {"type": "text", "text": f"## Task\n\n{task_prompt}"}
    ]

    if files:
        for i, file_b64 in enumerate(files):
            # Try to detect media type from the base64 header or default to image
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
                    }
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
                    }
                )

    return content


def _detect_media_type(b64_string: str) -> str:
    """Detect media type from a base64 string, possibly with data URI prefix."""
    if b64_string.startswith("data:"):
        # data:image/png;base64,...
        header = b64_string.split(",", 1)[0]
        media_type = header.split(":")[1].split(";")[0]
        return media_type

    # Try to detect from the first few bytes
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
# Agentic loop
# ---------------------------------------------------------------------------
def parse_and_execute_task(
    task_prompt: str,
    session: requests.Session,
    files: list[str] | None,
) -> None:
    """Run the Claude agentic loop to solve a Tripletex task.

    1. Send the task prompt (+ files) to Claude with tool definitions.
    2. When Claude returns tool_use blocks, execute them and feed results back.
    3. Repeat until Claude signals end_turn or we hit MAX_ITERATIONS.
    """
    client = anthropic.Anthropic()

    messages: list[anthropic.types.MessageParam] = [
        {"role": "user", "content": build_user_message(task_prompt, files)}
    ]

    for iteration in range(MAX_ITERATIONS):
        logger.info("Iteration %d", iteration + 1)

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=_FULL_SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Collect assistant content blocks
        assistant_content = response.content

        # Append the full assistant message
        messages.append({"role": "assistant", "content": assistant_content})

        # Check if we're done
        if response.stop_reason == "end_turn":
            logger.info("Agent finished (end_turn) after %d iterations", iteration + 1)
            return

        # Process tool use blocks
        tool_results: list[anthropic.types.ToolResultBlockParam] = []
        for block in assistant_content:
            if block.type == "tool_use":
                logger.info("Calling tool: %s(%s)", block.name, block.input)
                result = execute_tool(block.name, block.input, session)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            # No tool calls and not end_turn — shouldn't happen, but break to be safe
            logger.warning("No tool calls and stop_reason=%s, breaking", response.stop_reason)
            return

    logger.warning("Hit max iterations (%d), stopping", MAX_ITERATIONS)


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

    parse_and_execute_task(
        task_prompt=request.task_prompt,
        session=session,
        files=request.files,
    )

    return SolveResponse(status="completed")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
