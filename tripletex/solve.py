"""Tripletex AI Accounting Agent - FastAPI endpoint.

Deploy this as a Cloud Run service and register the URL at app.ainm.no.

Usage:
    uvicorn nmai.tasks.tripletex.solve:app --host 0.0.0.0 --port 8080
"""

from fastapi import FastAPI
from pydantic import BaseModel
import requests

app = FastAPI(title="Tripletex AI Agent")


class SolveRequest(BaseModel):
    task_prompt: str
    session_token: str
    base_url: str
    files: list[str] | None = None  # Optional base64-encoded PDFs/images


class SolveResponse(BaseModel):
    status: str


def get_tripletex_session(base_url: str, session_token: str) -> requests.Session:
    """Create an authenticated requests session for the Tripletex API."""
    session = requests.Session()
    session.auth = ("0", session_token)
    session.headers.update({"Content-Type": "application/json"})
    # Store base_url on the session for convenience
    session.base_url = base_url  # type: ignore[attr-defined]
    return session


def tripletex_get(
    session: requests.Session, endpoint: str, params: dict | None = None
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


def parse_and_execute_task(
    task_prompt: str, session: requests.Session, files: list[str] | None
) -> None:
    """Parse the task prompt and execute the appropriate Tripletex API calls.

    TODO: Implement task parsing and execution logic.
    This is the core of the agent - it needs to:
    1. Understand the task prompt (in 7 possible languages)
    2. Determine which Tripletex API calls to make
    3. Execute them in the correct order
    4. Minimize API calls and 4xx errors for efficiency bonus
    """
    raise NotImplementedError("Implement task parsing and execution logic")


@app.post("/solve", response_model=SolveResponse)
async def solve(request: SolveRequest) -> SolveResponse:
    """Main endpoint called by the competition platform."""
    session = get_tripletex_session(request.base_url, request.session_token)

    parse_and_execute_task(
        task_prompt=request.task_prompt,
        session=session,
        files=request.files,
    )

    return SolveResponse(status="completed")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
