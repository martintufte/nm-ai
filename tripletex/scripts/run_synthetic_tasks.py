"""Run synthetic tasks against the local solve endpoint.

Each task has unique names (UUID-suffixed) to avoid sandbox collisions.
Tasks that reference existing entities (update/delete) pre-create them via
direct API calls before sending the task to /solve.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httpx

BASE = "http://127.0.0.1:8099"
BEARER_TOKEN = os.environ["BEARER_TOKEN"]
TRIPLETEX_BASE_URL = os.environ["TRIPLETEX_SANDBOX_API_URL"]
TRIPLETEX_SESSION_TOKEN = os.environ["TRIPLETEX_SANDBOX_TOKEN"]

RESULTS_DIR = Path(__file__).resolve().parent.parent / "data"


def _tripletex_client() -> httpx.Client:
    return httpx.Client(
        base_url=TRIPLETEX_BASE_URL,
        auth=("0", TRIPLETEX_SESSION_TOKEN),
        headers={"Content-Type": "application/json"},
    )


def _uid() -> str:
    return uuid.uuid4().hex[:8]


SyntheticTask = dict[str, Any]


def build_tasks() -> list[SyntheticTask]:
    """Build task list with unique names and optional setup functions."""
    uid = _uid()

    # --- Task 1.1: Create Employee (needs pre-created department) ---
    emp_first = f"Ola{uid}"
    emp_last = f"Nordmann{uid}"
    emp_email = f"ola.{uid}@firma.no"
    dept_name_1 = f"Salg {uid}"

    def setup_task_1(client: httpx.Client) -> None:
        resp = client.post("department", json={"name": dept_name_1})
        resp.raise_for_status()
        print(f"  [setup] Created department '{dept_name_1}' (id={resp.json()['value']['id']})")

    # --- Task 2.1: Create Invoice (needs pre-created customer + product) ---
    cust_name_2 = f"Berge {uid} AS"
    prod_name_2 = f"Kontorstol {uid}"

    def setup_task_2(client: httpx.Client) -> None:
        resp = client.post("customer", json={"name": cust_name_2})
        resp.raise_for_status()
        print(f"  [setup] Created customer '{cust_name_2}' (id={resp.json()['value']['id']})")
        resp = client.post("product", json={"name": prod_name_2, "priceExcludingVatCurrency": 2500})
        resp.raise_for_status()
        print(f"  [setup] Created product '{prod_name_2}' (id={resp.json()['value']['id']})")

    # --- Task 3.1: Update Customer Address (needs pre-created customer) ---
    cust_name_3 = f"Fjord Consulting {uid}"

    def setup_task_3(client: httpx.Client) -> None:
        resp = client.post("customer", json={"name": cust_name_3})
        resp.raise_for_status()
        print(f"  [setup] Created customer '{cust_name_3}' (id={resp.json()['value']['id']})")

    # --- Task 4.1: Delete Department (needs pre-created department) ---
    dept_name_4 = f"Temporary Projects {uid}"

    def setup_task_4(client: httpx.Client) -> None:
        resp = client.post("department", json={"name": dept_name_4})
        resp.raise_for_status()
        print(f"  [setup] Created department '{dept_name_4}' (id={resp.json()['value']['id']})")

    # --- Task 5.1: Full Invoice with Payment ---
    cust_name_5 = f"Nordic Solutions {uid} AS"
    prod_name_5 = f"Consultoría TI {uid}"

    return [
        {
            "name": "1.1 Create Employee (Norwegian)",
            "prompt": (
                f'Opprett en ansatt ved navn {emp_first} {emp_last}, '
                f'født 15. mars 1988, e-post {emp_email}, startdato 1. april 2026, '
                f'avdeling "{dept_name_1}".'
            ),
            "setup": setup_task_1,
        },
        {
            "name": "2.1 Create Invoice (English)",
            "prompt": (
                f'Create an invoice dated March 25, 2026 due April 25, 2026 for customer '
                f'"{cust_name_2}" with 3 units of product "{prod_name_2}" at 2500 kr each.'
            ),
            "setup": setup_task_2,
        },
        {
            "name": "3.1 Update Customer Address (French)",
            "prompt": (
                f'Le client "{cust_name_3}" a déménagé. '
                f'Mettez à jour son adresse à Storgata 45, 0182 Oslo.'
            ),
            "setup": setup_task_3,
        },
        {
            "name": "4.1 Delete Department (German)",
            "prompt": f'Bitte löschen Sie die Abteilung "{dept_name_4}".',
            "setup": setup_task_4,
        },
        {
            "name": "5.1 Full Invoice with Payment (Spanish)",
            "prompt": (
                f'Cree un cliente "{cust_name_5}", un producto "{prod_name_5}" a 1200 kr, '
                f'y genere una factura con fecha 20 de marzo de 2026, vencimiento 20 de abril de 2026, '
                f'con 10 unidades del producto. Luego registre el pago completo con fecha 20 de marzo de 2026.'
            ),
        },
    ]


def run_task(task: SyntheticTask, tx_client: httpx.Client) -> dict:
    print(f"\n{'='*60}")
    print(f"TASK: {task['name']}")
    print(f"{'='*60}")
    print(f"Prompt: {task['prompt'][:120]}...")

    # Run setup if present
    setup_fn: Callable[[httpx.Client], None] | None = task.get("setup")
    if setup_fn is not None:
        setup_fn(tx_client)

    start = time.time()
    resp = httpx.post(
        f"{BASE}/solve",
        headers={"Authorization": f"Bearer {BEARER_TOKEN}"},
        json={
            "prompt": task["prompt"],
            "tripletex_credentials": {
                "base_url": TRIPLETEX_BASE_URL,
                "session_token": TRIPLETEX_SESSION_TOKEN,
            },
        },
        timeout=300,
    )
    elapsed = time.time() - start

    result = {
        "name": task["name"],
        "status_code": resp.status_code,
        "elapsed_s": round(elapsed, 1),
        "response": resp.json() if resp.status_code == 200 else resp.text,
    }
    print(f"Status: {resp.status_code} | Time: {elapsed:.1f}s")
    return result


def print_summary(results: list[dict]) -> None:
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Task':<45} {'Status':<8} {'Time':>8}")
    print(f"  {'-'*45} {'-'*8} {'-'*8}")
    for r in results:
        status = "OK" if r["status_code"] == 200 else "FAIL"
        print(f"  {r['name']:<45} {status:<8} {r['elapsed_s']:>7.1f}s")

    ok = sum(1 for r in results if r["status_code"] == 200)
    total = len(results)
    print(f"\n  {ok}/{total} tasks completed successfully")


def save_results(results: list[dict]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"synthetic_results_{ts}.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {path}")
    return path


if __name__ == "__main__":
    tasks = build_tasks()
    tx_client = _tripletex_client()

    results = []
    for task in tasks:
        result = run_task(task, tx_client)
        results.append(result)

    print_summary(results)
    save_results(results)
