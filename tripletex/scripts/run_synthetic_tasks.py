"""Run synthetic tasks against the solve endpoint or a local Claude Code subagent.

Each task has unique names (UUID-suffixed) to avoid sandbox collisions.
Tasks that reference existing entities (update/delete) pre-create them via
direct API calls before sending the task to /solve.

Usage:
    # Against the HTTP solve server (default):
    python run_synthetic_tasks.py

    # Against a local Claude Code subagent (uses Claude Code billing):
    python run_synthetic_tasks.py --local
    python run_synthetic_tasks.py --local --model sonnet  # override model
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx

BASE = "http://127.0.0.1:8099"
TRIPLETEX_BASE_URL = os.environ["TRIPLETEX_SANDBOX_API_URL"]
TRIPLETEX_SESSION_TOKEN = os.environ["TRIPLETEX_SANDBOX_TOKEN"]

RESULTS_DIR = Path(__file__).resolve().parent.parent / "data"
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent


def _tripletex_client() -> httpx.Client:
    return httpx.Client(
        base_url=TRIPLETEX_BASE_URL,
        auth=("0", TRIPLETEX_SESSION_TOKEN),
        headers={"Content-Type": "application/json"},
    )


def _uid() -> str:
    return uuid.uuid4().hex[:8]


SyntheticTask = dict[str, Any]
VerifyCheck = tuple[str, bool, str]  # (check_name, passed, detail)


def _make_pdf(text_lines: list[str]) -> bytes:
    """Create a minimal valid PDF containing the given text lines."""
    buf = io.BytesIO()
    offsets: dict[int, int] = {}

    def w(s: str) -> None:
        buf.write(s.encode("latin-1"))

    w("%PDF-1.4\n")

    offsets[1] = buf.tell()
    w("1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n")

    offsets[2] = buf.tell()
    w("2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n")

    # Content stream (text lines rendered top-down)
    content_parts = []
    y = 750
    for line in text_lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_parts.append(f"BT /F1 11 Tf 50 {y} Td ({escaped}) Tj ET")
        y -= 16
    content = "\n".join(content_parts)

    offsets[4] = buf.tell()
    w(f"4 0 obj<</Length {len(content)}>>stream\n{content}\nendstream endobj\n")

    offsets[3] = buf.tell()
    w(
        "3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        "/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>"
        "/Contents 4 0 R>>endobj\n",
    )

    xref_pos = buf.tell()
    n = max(offsets) + 1
    w("xref\n")
    w(f"0 {n}\n")
    w("0000000000 65535 f \n")
    for i in range(1, n):
        w(f"{offsets[i]:010d} 00000 n \n")
    w(f"trailer<</Size {n}/Root 1 0 R>>\n")
    w("startxref\n")
    w(f"{xref_pos}\n")
    w("%%EOF\n")

    return buf.getvalue()


def _verify_checks(checks: list[VerifyCheck]) -> dict:
    """Summarize verify checks into a result dict."""
    passed = sum(1 for _, ok, _ in checks if ok)
    failed = [f"  FAIL: {name}: {detail}" for name, ok, detail in checks if not ok]
    return {
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
        "failures": failed,
    }


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

    def verify_task_1(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get(
            "employee",
            params={
                "firstName": emp_first,
                "lastName": emp_last,
                "count": 5,
                "fields": "id,email,employments(*)",
            },
        )
        vals = resp.json().get("values", [])
        if not vals:
            return [
                ("employee_exists", False, f"No employee found with name {emp_first} {emp_last}"),
            ]
        emp = vals[0]
        checks: list[VerifyCheck] = [
            ("employee_exists", True, f"id={emp['id']}"),
            (
                "email",
                emp.get("email") == emp_email,
                f"expected {emp_email}, got {emp.get('email')}",
            ),
        ]
        # Check employment start date
        emps = emp.get("employments", [])
        has_start = any(e.get("startDate") == "2026-04-01" for e in emps)
        checks.append(("employment_start_date", has_start, "expected 2026-04-01 in employments"))
        return checks

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

    def verify_task_2(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("customer", params={"customerName": cust_name_2, "count": 5})
        custs = resp.json().get("values", [])
        if not custs:
            return [("customer_exists", False, f"No customer '{cust_name_2}'")]
        cust_id = custs[0]["id"]
        resp = client.get(
            "invoice",
            params={
                "customerId": cust_id,
                "invoiceDateFrom": "2020-01-01",
                "invoiceDateTo": "2030-01-01",
                "count": 5,
            },
        )
        invoices = resp.json().get("values", [])
        if not invoices:
            return [
                ("customer_exists", True, ""),
                ("invoice_exists", False, "No invoice found for customer"),
            ]
        inv = invoices[0]
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust_id}"),
            ("invoice_exists", True, f"id={inv['id']}"),
            (
                "invoice_date",
                inv.get("invoiceDate") == "2026-03-25",
                f"expected 2026-03-25, got {inv.get('invoiceDate')}",
            ),
        ]
        # Check order lines via the order
        orders = inv.get("orders", [])
        if orders:
            order_id = orders[0].get("id")
            resp = client.get(f"order/{order_id}", params={"fields": "orderLines(*)"})
            order = resp.json().get("value", {})
            lines = order.get("orderLines", [])
            has_3_units = any(line.get("count") == 3 for line in lines)
            checks.append(
                (
                    "order_line_count_3",
                    has_3_units,
                    f"lines: {[(line.get('count'), line.get('unitPriceExcludingVatCurrency')) for line in lines]}",
                ),
            )
        return checks

    # --- Task 3.1: Update Customer Address (needs pre-created customer) ---
    cust_name_3 = f"Fjord Consulting {uid}"

    def setup_task_3(client: httpx.Client) -> None:
        resp = client.post("customer", json={"name": cust_name_3})
        resp.raise_for_status()
        print(f"  [setup] Created customer '{cust_name_3}' (id={resp.json()['value']['id']})")

    def verify_task_3(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get(
            "customer",
            params={"customerName": cust_name_3, "count": 5, "fields": "id,postalAddress(*)"},
        )
        custs = resp.json().get("values", [])
        if not custs:
            return [("customer_exists", False, f"No customer '{cust_name_3}'")]
        cust = custs[0]
        addr = cust.get("postalAddress", {}) or {}
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust['id']}"),
            (
                "address_line",
                addr.get("addressLine1") == "Storgata 45",
                f"expected 'Storgata 45', got {addr.get('addressLine1')!r}",
            ),
            (
                "postal_code",
                addr.get("postalCode") == "0182",
                f"expected '0182', got {addr.get('postalCode')!r}",
            ),
            ("city", addr.get("city") == "Oslo", f"expected 'Oslo', got {addr.get('city')!r}"),
        ]
        return checks

    # --- Task 4.1: Delete Department (needs pre-created department) ---
    dept_name_4 = f"Temporary Projects {uid}"

    def setup_task_4(client: httpx.Client) -> None:
        resp = client.post("department", json={"name": dept_name_4})
        resp.raise_for_status()
        print(f"  [setup] Created department '{dept_name_4}' (id={resp.json()['value']['id']})")

    def verify_task_4(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("department", params={"name": dept_name_4, "count": 5})
        vals = resp.json().get("values", [])
        return [
            (
                "department_deleted",
                len(vals) == 0,
                f"found {len(vals)} departments named '{dept_name_4}'",
            ),
        ]

    # --- Task 5.1: Full Invoice with Payment ---
    cust_name_5 = f"Nordic Solutions {uid} AS"
    prod_name_5 = f"Consultoría TI {uid}"

    def verify_task_5(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("customer", params={"customerName": cust_name_5, "count": 5})
        custs = resp.json().get("values", [])
        if not custs:
            return [("customer_exists", False, f"No customer '{cust_name_5}'")]
        cust_id = custs[0]["id"]
        resp = client.get(
            "invoice",
            params={
                "customerId": cust_id,
                "invoiceDateFrom": "2020-01-01",
                "invoiceDateTo": "2030-01-01",
                "count": 5,
            },
        )
        invoices = resp.json().get("values", [])
        if not invoices:
            return [("customer_exists", True, ""), ("invoice_exists", False, "No invoice found")]
        inv = invoices[0]
        amount = inv.get("amountExcludingVat")
        expected_amount = 10 * 1200  # 10 units * 1200 kr (excl. VAT)
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust_id}"),
            ("invoice_exists", True, f"id={inv['id']}"),
            (
                "amount_excl_vat",
                amount == expected_amount,
                f"expected {expected_amount}, got {amount}",
            ),
            (
                "is_paid",
                inv.get("amountOutstanding") == 0,
                f"outstanding={inv.get('amountOutstanding')}",
            ),
        ]
        return checks

    # --- Task 6.1: Create Project (needs pre-created customer, employee as participant) ---
    # NOTE: projectManager requires AUTH_PROJECT_MANAGER entitlement, which only the
    # admin employee has. We use the admin as PM (via GET /token/session/>whoAmI)
    # and the pre-created employee as a participant to keep the task interesting.
    proj_name_6 = f"Upgrade Silveroak {uid}"
    cust_name_6 = f"Silveroak {uid} AS"
    emp_first_6 = f"Alice{uid}"
    emp_last_6 = f"Smith{uid}"
    emp_email_6 = f"alice.{uid}@firma.no"
    dept_name_6 = f"Engineering {uid}"

    def setup_task_6(client: httpx.Client) -> None:
        resp = client.post("department", json={"name": dept_name_6})
        resp.raise_for_status()
        dept_id = resp.json()["value"]["id"]
        print(f"  [setup] Created department '{dept_name_6}' (id={dept_id})")

        resp = client.post(
            "employee",
            json={
                "firstName": emp_first_6,
                "lastName": emp_last_6,
                "email": emp_email_6,
                "userType": "NO_ACCESS",
                "department": {"id": dept_id},
            },
        )
        resp.raise_for_status()
        print(
            f"  [setup] Created employee '{emp_first_6} {emp_last_6}' (id={resp.json()['value']['id']})",
        )

        resp = client.post("customer", json={"name": cust_name_6})
        resp.raise_for_status()
        print(f"  [setup] Created customer '{cust_name_6}' (id={resp.json()['value']['id']})")

    def verify_task_6(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("project", params={"name": proj_name_6, "count": 5})
        projs = resp.json().get("values", [])
        if not projs:
            return [("project_exists", False, f"No project '{proj_name_6}'")]
        proj = projs[0]
        checks: list[VerifyCheck] = [
            ("project_exists", True, f"id={proj['id']}"),
        ]
        # Check customer link
        proj_cust = proj.get("customer", {}) or {}
        resp2 = client.get("customer", params={"customerName": cust_name_6, "count": 5})
        expected_cust_id = resp2.json()["values"][0]["id"] if resp2.json().get("values") else None
        checks.append(
            (
                "customer_linked",
                proj_cust.get("id") == expected_cust_id,
                f"expected cust_id={expected_cust_id}, got {proj_cust.get('id')}",
            ),
        )
        # Check participant
        resp3 = client.get(f"project/{proj['id']}", params={"fields": "participants(employee(*))"})
        participants = resp3.json().get("value", {}).get("participants", [])
        participant_emails = [p.get("employee", {}).get("email") for p in participants]
        checks.append(
            (
                "participant_added",
                emp_email_6 in participant_emails,
                f"expected {emp_email_6} in {participant_emails}",
            ),
        )
        return checks

    # --- Task 7.1: Run Payroll via Manual Voucher (needs pre-created employee) ---
    emp_first_7 = f"James{uid}"
    emp_last_7 = f"Williams{uid}"
    emp_email_7 = f"james.{uid}@firma.no"
    dept_name_7 = f"Finance {uid}"

    def setup_task_7(client: httpx.Client) -> None:
        resp = client.post("department", json={"name": dept_name_7})
        resp.raise_for_status()
        dept_id = resp.json()["value"]["id"]
        print(f"  [setup] Created department '{dept_name_7}' (id={dept_id})")

        resp = client.post(
            "employee",
            json={
                "firstName": emp_first_7,
                "lastName": emp_last_7,
                "email": emp_email_7,
                "userType": "NO_ACCESS",
                "department": {"id": dept_id},
            },
        )
        resp.raise_for_status()
        print(
            f"  [setup] Created employee '{emp_first_7} {emp_last_7}' (id={resp.json()['value']['id']})",
        )

    def verify_task_7(client: httpx.Client) -> list[VerifyCheck]:
        total_salary = 34950 + 15450  # base + bonus = 50400
        today = datetime.now(tz=UTC).date()
        tomorrow = today + timedelta(days=1)
        # Find the employee ID for later matching
        emp_resp = client.get(
            "employee",
            params={"firstName": emp_first_7, "lastName": emp_last_7, "count": 1},
        )
        emp_values = emp_resp.json().get("values", [])
        expected_emp_id = emp_values[0]["id"] if emp_values else None
        # Find recent vouchers — dateFrom/dateTo required, dateTo is exclusive
        resp = client.get(
            "ledger/voucher",
            params={
                "dateFrom": today.isoformat(),
                "dateTo": tomorrow.isoformat(),
                "count": 200,
            },
        )
        vouchers = resp.json().get("values", [])
        # Search newest first (highest ID) to avoid picking up stale vouchers from prior runs
        vouchers.sort(key=lambda v: v["id"], reverse=True)
        # Find a voucher with salary postings linked to the expected employee
        target_voucher = None
        target_postings = None
        fallback_voucher = None
        fallback_postings = None
        for v in vouchers:
            postings = v.get("postings", [])
            # Postings in listing are stubs — fetch with expanded fields
            if postings and not postings[0].get("account", {}).get("number"):
                resp2 = client.get(
                    f"ledger/voucher/{v['id']}",
                    params={"fields": "postings(*,account(*),employee(*))"},
                )
                postings = resp2.json().get("value", {}).get("postings", [])
            for p in postings:
                acct_num = p.get("account", {}).get("number", 0)
                if 5000 <= acct_num < 6000 and abs(p.get("amountGross", 0)) > 0:
                    emp = p.get("employee")
                    if emp and emp.get("id") == expected_emp_id:
                        target_voucher = v
                        target_postings = postings
                    elif fallback_voucher is None:
                        fallback_voucher = v
                        fallback_postings = postings
                    break
            if target_voucher:
                break
        # Use employee-matched voucher if found, otherwise fall back to any salary voucher
        if not target_voucher:
            target_voucher = fallback_voucher
            target_postings = fallback_postings
        if not target_voucher or target_postings is None:
            return [
                (
                    "voucher_exists",
                    False,
                    f"No voucher with 5000-series account found among {len(vouchers)} vouchers on {today}",
                ),
            ]
        debit_total = sum(
            p.get("amountGross", 0) for p in target_postings if p.get("amountGross", 0) > 0
        )
        credit_total = sum(
            p.get("amountGross", 0) for p in target_postings if p.get("amountGross", 0) < 0
        )
        # Check employee association on salary posting (5000-series debit)
        salary_posting = next(
            (
                p
                for p in target_postings
                if 5000 <= p.get("account", {}).get("number", 0) < 6000
                and p.get("amountGross", 0) > 0
            ),
            None,
        )
        posting_emp = salary_posting.get("employee") if salary_posting else None
        posting_emp_id = posting_emp.get("id") if posting_emp else None
        checks: list[VerifyCheck] = [
            ("voucher_exists", True, f"id={target_voucher['id']}"),
            (
                "debit_amount",
                debit_total == total_salary,
                f"expected {total_salary}, got {debit_total}",
            ),
            (
                "credit_amount",
                credit_total == -total_salary,
                f"expected {-total_salary}, got {credit_total}",
            ),
            (
                "balanced",
                debit_total + credit_total == 0,
                f"debit={debit_total} credit={credit_total}",
            ),
            (
                "employee_linked",
                posting_emp_id == expected_emp_id,
                f"expected employee {expected_emp_id}, got {posting_emp_id}",
            ),
        ]
        return checks

    # --- Task 8.1: Timesheet + Project Invoice (needs project, employee, activity, customer, bank account) ---
    proj_name_8 = f"Integración {uid}"
    cust_name_8 = f"Costa Brava {uid} SL"
    emp_first_8 = f"Ana{uid}"
    emp_last_8 = f"Romero{uid}"
    emp_email_8 = f"ana.{uid}@firma.no"
    dept_name_8 = f"Consulting {uid}"
    activity_name_8 = f"Design {uid}"

    def setup_task_8(client: httpx.Client) -> None:
        # Department (employee dependency)
        resp = client.post("department", json={"name": dept_name_8})
        resp.raise_for_status()
        dept_id = resp.json()["value"]["id"]
        print(f"  [setup] Created department '{dept_name_8}' (id={dept_id})")

        # Employee (for timesheet registration — NO_ACCESS is fine, not the PM)
        resp = client.post(
            "employee",
            json={
                "firstName": emp_first_8,
                "lastName": emp_last_8,
                "email": emp_email_8,
                "userType": "NO_ACCESS",
                "department": {"id": dept_id},
            },
        )
        resp.raise_for_status()
        print(
            f"  [setup] Created employee '{emp_first_8} {emp_last_8}' (id={resp.json()['value']['id']})",
        )

        # Customer
        resp = client.post("customer", json={"name": cust_name_8})
        resp.raise_for_status()
        cust_id = resp.json()["value"]["id"]
        print(f"  [setup] Created customer '{cust_name_8}' (id={cust_id})")

        # Activity
        resp = client.post(
            "activity",
            json={"name": activity_name_8, "activityType": "PROJECT_GENERAL_ACTIVITY"},
        )
        resp.raise_for_status()
        activity_id = resp.json()["value"]["id"]
        print(f"  [setup] Created activity '{activity_name_8}' (id={activity_id})")

        # Use logged-in employee as PM (has required entitlements)
        resp = client.get("token/session/>whoAmI")
        resp.raise_for_status()
        pm_id = resp.json()["value"]["employeeId"]
        print(f"  [setup] Using admin employee as PM (id={pm_id})")

        # Project (external, linked to customer, with project activity)
        resp = client.post(
            "project",
            json={
                "name": proj_name_8,
                "projectManager": {"id": pm_id},
                "isInternal": False,
                "startDate": "2026-01-01",
                "customer": {"id": cust_id},
                "projectActivities": [{"activity": {"id": activity_id}}],
            },
        )
        resp.raise_for_status()
        print(f"  [setup] Created project '{proj_name_8}' (id={resp.json()['value']['id']})")

        # Ensure at least one bank account has a number (required for invoicing)
        resp = client.get("ledger/account", params={"isBankAccount": True, "count": 5})
        resp.raise_for_status()
        bank_accounts = resp.json()["values"]
        has_bank_number = any(a.get("bankAccountNumber") for a in bank_accounts)
        if not has_bank_number and bank_accounts:
            acct = bank_accounts[0]
            resp2 = client.put(
                f"ledger/account/{acct['id']}",
                json={
                    "id": acct["id"],
                    "version": acct["version"],
                    "bankAccountNumber": "12345678903",
                },
            )
            resp2.raise_for_status()
            print(
                f"  [setup] Set bank account number on account {acct['number']} (id={acct['id']})",
            )

    def verify_task_8(client: httpx.Client) -> list[VerifyCheck]:
        checks: list[VerifyCheck] = []
        # Check timesheet entry
        resp = client.get(
            "employee",
            params={"firstName": emp_first_8, "lastName": emp_last_8, "count": 5},
        )
        emps = resp.json().get("values", [])
        if not emps:
            return [("employee_found", False, f"No employee '{emp_first_8} {emp_last_8}'")]
        emp_id = emps[0]["id"]
        resp = client.get(
            "timesheet/entry",
            params={
                "employeeId": emp_id,
                "dateFrom": "2020-01-01",
                "dateTo": "2030-01-01",
                "count": 50,
            },
        )
        entries = resp.json().get("values", [])
        has_11h = any(e.get("hours") == 11 for e in entries)
        checks.append(
            ("timesheet_11h", has_11h, f"entries hours: {[e.get('hours') for e in entries]}"),
        )
        # Check invoice for customer
        resp = client.get("customer", params={"customerName": cust_name_8, "count": 5})
        custs = resp.json().get("values", [])
        if custs:
            cust_id = custs[0]["id"]
            resp = client.get(
                "invoice",
                params={
                    "customerId": cust_id,
                    "invoiceDateFrom": "2020-01-01",
                    "invoiceDateTo": "2030-01-01",
                    "count": 5,
                },
            )
            invoices = resp.json().get("values", [])
            checks.append(("invoice_exists", len(invoices) > 0, f"found {len(invoices)} invoices"))
        else:
            checks.append(("invoice_exists", False, "customer not found"))
        return checks

    # --- Helper: ensure bank account has a number (reused by tasks 9, 10, 11) ---
    def _ensure_bank_account(client: httpx.Client) -> None:
        resp = client.get("ledger/account", params={"isBankAccount": True, "count": 5})
        resp.raise_for_status()
        bank_accounts = resp.json()["values"]
        has_bank_number = any(a.get("bankAccountNumber") for a in bank_accounts)
        if not has_bank_number and bank_accounts:
            acct = bank_accounts[0]
            resp2 = client.put(
                f"ledger/account/{acct['id']}",
                json={
                    "id": acct["id"],
                    "version": acct["version"],
                    "bankAccountNumber": "12345678903",
                },
            )
            resp2.raise_for_status()
            print(
                f"  [setup] Set bank account number on account {acct['number']} (id={acct['id']})",
            )

    # --- Task 9.1: Multi-line Invoice with Org# + Product# + Mixed VAT (Norwegian) ---
    cust_name_9 = f"Havfjord Teknikk {uid} AS"
    org_nr_9 = "9" + uid[:8].translate(str.maketrans("abcdef", "123456"))
    _uid_int = int(uid, 16) % 90000 + 10000  # 5-digit number from uid
    prod_name_9a = f"Industriventil {uid}"
    prod_num_9a = str(100000 + _uid_int)
    prod_name_9b = f"Økologisk Granola {uid}"
    prod_num_9b = str(200000 + _uid_int)
    prod_name_9c = f"Helsetjeneste {uid}"
    prod_num_9c = str(300000 + _uid_int)

    def setup_task_9(client: httpx.Client) -> None:
        resp = client.post("customer", json={"name": cust_name_9, "organizationNumber": org_nr_9})
        resp.raise_for_status()
        print(
            f"  [setup] Created customer '{cust_name_9}' org={org_nr_9} (id={resp.json()['value']['id']})",
        )

        for name, num in [
            (prod_name_9a, prod_num_9a),
            (prod_name_9b, prod_num_9b),
            (prod_name_9c, prod_num_9c),
        ]:
            resp = client.post(
                "product",
                json={"name": name, "number": int(num), "priceExcludingVatCurrency": 0},
            )
            resp.raise_for_status()
            print(
                f"  [setup] Created product '{name}' number={num} (id={resp.json()['value']['id']})",
            )

        _ensure_bank_account(client)

    def verify_task_9(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("customer", params={"organizationNumber": org_nr_9, "count": 5})
        custs = resp.json().get("values", [])
        if not custs:
            return [("customer_exists", False, f"No customer with org {org_nr_9}")]
        cust_id = custs[0]["id"]
        resp = client.get(
            "invoice",
            params={
                "customerId": cust_id,
                "invoiceDateFrom": "2020-01-01",
                "invoiceDateTo": "2030-01-01",
                "count": 5,
            },
        )
        invoices = resp.json().get("values", [])
        if not invoices:
            return [("customer_exists", True, ""), ("invoice_exists", False, "No invoice found")]
        inv = invoices[0]
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust_id}"),
            ("invoice_exists", True, f"id={inv['id']}"),
            (
                "invoice_date",
                inv.get("invoiceDate") == "2026-04-01",
                f"got {inv.get('invoiceDate')}",
            ),
        ]
        # Check 3 order lines
        orders = inv.get("orders", [])
        if orders:
            resp2 = client.get(f"order/{orders[0]['id']}", params={"fields": "orderLines(*)"})
            lines = resp2.json().get("value", {}).get("orderLines", [])
            checks.append(("three_lines", len(lines) == 3, f"got {len(lines)} lines"))
        return checks

    # --- Task 10.1: Fixed-price Project + Milestone Invoice (German) ---
    proj_name_10 = f"Gebäudeautomation {uid}"
    cust_name_10 = f"Berliner Bau {uid} GmbH"
    dept_name_10 = f"Projekte {uid}"
    emp_first_10 = f"Max{uid}"
    emp_last_10 = f"Weber{uid}"
    emp_email_10 = f"max.{uid}@firma.no"

    def setup_task_10(client: httpx.Client) -> None:
        resp = client.post("department", json={"name": dept_name_10})
        resp.raise_for_status()
        dept_id = resp.json()["value"]["id"]
        print(f"  [setup] Created department '{dept_name_10}' (id={dept_id})")

        resp = client.post(
            "employee",
            json={
                "firstName": emp_first_10,
                "lastName": emp_last_10,
                "email": emp_email_10,
                "userType": "NO_ACCESS",
                "department": {"id": dept_id},
            },
        )
        resp.raise_for_status()
        print(
            f"  [setup] Created employee '{emp_first_10} {emp_last_10}' (id={resp.json()['value']['id']})",
        )

        org_nr_10 = "8" + uid[:8].translate(str.maketrans("abcdef", "123456"))
        resp = client.post("customer", json={"name": cust_name_10, "organizationNumber": org_nr_10})
        resp.raise_for_status()
        cust_id = resp.json()["value"]["id"]
        print(f"  [setup] Created customer '{cust_name_10}' (id={cust_id})")

        resp = client.get("token/session/>whoAmI")
        resp.raise_for_status()
        pm_id = resp.json()["value"]["employeeId"]
        print(f"  [setup] Using admin employee as PM (id={pm_id})")

        resp = client.post(
            "project",
            json={
                "name": proj_name_10,
                "projectManager": {"id": pm_id},
                "isInternal": False,
                "startDate": "2026-01-01",
                "customer": {"id": cust_id},
            },
        )
        resp.raise_for_status()
        print(f"  [setup] Created project '{proj_name_10}' (id={resp.json()['value']['id']})")

        _ensure_bank_account(client)

    def verify_task_10(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("project", params={"name": proj_name_10, "count": 5})
        projs = resp.json().get("values", [])
        if not projs:
            return [("project_exists", False, f"No project '{proj_name_10}'")]
        proj = projs[0]
        checks: list[VerifyCheck] = [
            ("project_exists", True, f"id={proj['id']}"),
            (
                "is_fixed_price",
                proj.get("isFixedPrice") is True,
                f"isFixedPrice={proj.get('isFixedPrice')}",
            ),
            (
                "fixed_price_amount",
                proj.get("fixedprice") == 473250,
                f"expected 473250, got {proj.get('fixedprice')}",
            ),
        ]
        # Check milestone invoice (25% of 473250 = 118312.50)
        cust = proj.get("customer", {}) or {}
        if cust.get("id"):
            resp2 = client.get(
                "invoice",
                params={
                    "customerId": cust["id"],
                    "invoiceDateFrom": "2020-01-01",
                    "invoiceDateTo": "2030-01-01",
                    "count": 5,
                },
            )
            invoices = resp2.json().get("values", [])
            checks.append(("invoice_exists", len(invoices) > 0, f"found {len(invoices)} invoices"))
            if invoices:
                # Check amount is ~25% of 473250
                expected = 473250 * 0.25
                amount = invoices[0].get("amount", 0)
                checks.append(
                    (
                        "milestone_amount",
                        abs(amount - expected) < 1,
                        f"expected ~{expected}, got {amount}",
                    ),
                )
        return checks

    # --- Task 11.1: Order → Invoice Conversion + Payment (German) ---
    cust_name_11 = f"Hamburger Handel {uid} GmbH"
    org_nr_11 = "7" + uid[:8].translate(str.maketrans("abcdef", "123456"))
    prod_name_11a = f"Serverschrank {uid}"
    prod_num_11a = str(400000 + _uid_int)
    prod_name_11b = f"Netzwerkkabel {uid}"
    prod_num_11b = str(500000 + _uid_int)

    def setup_task_11(client: httpx.Client) -> None:
        resp = client.post("customer", json={"name": cust_name_11, "organizationNumber": org_nr_11})
        resp.raise_for_status()
        cust_id = resp.json()["value"]["id"]
        print(
            f"  [setup] Created customer '{cust_name_11}' org={org_nr_11} (id={cust_id})",
        )

        prod_ids = []
        for name, num, price in [
            (prod_name_11a, prod_num_11a, 20400),
            (prod_name_11b, prod_num_11b, 15250),
        ]:
            resp = client.post(
                "product",
                json={"name": name, "number": int(num), "priceExcludingVatCurrency": price},
            )
            resp.raise_for_status()
            prod_ids.append(resp.json()["value"]["id"])
            print(
                f"  [setup] Created product '{name}' number={num} price={price} (id={prod_ids[-1]})",
            )

        # Pre-create the order so the agent must use PUT /order/:invoice to convert it
        resp = client.post(
            "order",
            json={
                "orderDate": "2026-04-01",
                "deliveryDate": "2026-04-01",
                "customer": {"id": cust_id},
                "orderLines": [
                    {"product": {"id": prod_ids[0]}, "count": 1},
                    {"product": {"id": prod_ids[1]}, "count": 1},
                ],
            },
        )
        resp.raise_for_status()
        order_id = resp.json()["value"]["id"]
        print(f"  [setup] Created order (id={order_id})")

        _ensure_bank_account(client)

    def verify_task_11(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("customer", params={"organizationNumber": org_nr_11, "count": 5})
        custs = resp.json().get("values", [])
        if not custs:
            return [("customer_exists", False, f"No customer with org {org_nr_11}")]
        cust_id = custs[0]["id"]

        # Check the order was converted (isClosed after :invoice)
        resp = client.get(
            "order",
            params={
                "customerId": cust_id,
                "orderDateFrom": "2020-01-01",
                "orderDateTo": "2030-01-01",
                "count": 5,
            },
        )
        orders = resp.json().get("values", [])
        order_closed = False
        if orders:
            order_closed = orders[0].get("isClosed", False)

        resp = client.get(
            "invoice",
            params={
                "customerId": cust_id,
                "invoiceDateFrom": "2020-01-01",
                "invoiceDateTo": "2030-01-01",
                "count": 5,
            },
        )
        invoices = resp.json().get("values", [])
        if not invoices:
            return [
                ("customer_exists", True, ""),
                ("order_converted", order_closed, "order not closed" if not order_closed else ""),
                ("invoice_exists", False, "No invoice found"),
            ]
        inv = invoices[0]
        expected_total = 20400 + 15250  # 35650
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust_id}"),
            ("order_converted", order_closed, f"isClosed={order_closed}"),
            ("invoice_exists", True, f"id={inv['id']}"),
            (
                "amount_ex_vat",
                inv.get("amountExcludingVat") == expected_total,
                f"expected {expected_total}, got {inv.get('amountExcludingVat')}",
            ),
            (
                "is_paid",
                inv.get("amountOutstanding") == 0,
                f"outstanding={inv.get('amountOutstanding')}",
            ),
        ]
        return checks

    # --- Task 12.1: Credit Note for Invoice (French) ---
    cust_name_12 = f"Bordeaux Consulting {uid} SAS"

    def setup_task_12(client: httpx.Client) -> None:
        _ensure_bank_account(client)
        resp = client.post("customer", json={"name": cust_name_12})
        resp.raise_for_status()
        cust_id = resp.json()["value"]["id"]
        print(f"  [setup] Created customer '{cust_name_12}' (id={cust_id})")
        resp = client.post(
            "invoice",
            json={
                "invoiceDate": "2026-03-15",
                "invoiceDueDate": "2026-04-15",
                "customer": {"id": cust_id},
                "orders": [
                    {
                        "orderDate": "2026-03-15",
                        "deliveryDate": "2026-03-15",
                        "customer": {"id": cust_id},
                        "orderLines": [
                            {
                                "description": "Service annuel",
                                "count": 1,
                                "unitPriceExcludingVatCurrency": 18000,
                            },
                        ],
                    },
                ],
            },
        )
        resp.raise_for_status()
        inv_id = resp.json()["value"]["id"]
        print(f"  [setup] Created invoice (id={inv_id})")

    def verify_task_12(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("customer", params={"customerName": cust_name_12, "count": 5})
        custs = resp.json().get("values", [])
        if not custs:
            return [("customer_exists", False, f"No customer '{cust_name_12}'")]
        cust_id = custs[0]["id"]
        resp = client.get(
            "invoice",
            params={
                "customerId": cust_id,
                "invoiceDateFrom": "2020-01-01",
                "invoiceDateTo": "2030-01-01",
                "count": 10,
            },
        )
        invoices = resp.json().get("values", [])
        # There should be 2 invoices: the original and the credit note
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust_id}"),
            (
                "has_credit_note",
                len(invoices) >= 2,
                f"expected >=2 invoices (original + credit note), got {len(invoices)}",
            ),
        ]
        if len(invoices) >= 2:
            # Credit note should have negative amount
            has_negative = any(inv.get("amountExcludingVat", 0) < 0 for inv in invoices)
            checks.append(
                (
                    "credit_note_negative",
                    has_negative,
                    "expected a credit note with negative amount",
                ),
            )
        return checks

    # --- Task 14.1: Project + Activity + Timesheet for 2 existing employees (Norwegian) ---
    # Tests that agent does NOT call GET /department when employees are pre-existing.
    proj_name_14 = f"Skymigrering {uid}"
    emp_first_14a = f"Maja{uid}"
    emp_last_14a = f"Lund{uid}"
    emp_email_14a = f"maja.{uid}@firma.no"
    emp_first_14b = f"Eirik{uid}"
    emp_last_14b = f"Vik{uid}"
    emp_email_14b = f"eirik.{uid}@firma.no"
    activity_name_14 = f"Backend {uid}"
    dept_name_14 = f"Platform {uid}"

    def setup_task_14(client: httpx.Client) -> None:
        # Department needed for employee creation, but agent should NOT look it up
        resp = client.post("department", json={"name": dept_name_14})
        resp.raise_for_status()
        dept_id = resp.json()["value"]["id"]
        print(f"  [setup] Created department '{dept_name_14}' (id={dept_id})")

        for first, last, email in [
            (emp_first_14a, emp_last_14a, emp_email_14a),
            (emp_first_14b, emp_last_14b, emp_email_14b),
        ]:
            resp = client.post(
                "employee",
                json={
                    "firstName": first,
                    "lastName": last,
                    "email": email,
                    "userType": "NO_ACCESS",
                    "department": {"id": dept_id},
                },
            )
            resp.raise_for_status()
            print(f"  [setup] Created employee '{first} {last}' (id={resp.json()['value']['id']})")

    def verify_task_14(client: httpx.Client) -> list[VerifyCheck]:
        checks: list[VerifyCheck] = []
        # Project exists
        resp = client.get("project", params={"name": proj_name_14, "count": 5})
        projs = resp.json().get("values", [])
        if not projs:
            return [("project_exists", False, f"No project '{proj_name_14}'")]
        proj = projs[0]
        checks.append(("project_exists", True, f"id={proj['id']}"))

        # Both employees are participants
        resp2 = client.get(
            f"project/{proj['id']}", params={"fields": "participants(employee(*))"}
        )
        participants = resp2.json().get("value", {}).get("participants", [])
        participant_emails = [p.get("employee", {}).get("email") for p in participants]
        for email, label in [
            (emp_email_14a, "participant_a"),
            (emp_email_14b, "participant_b"),
        ]:
            checks.append(
                (label, email in participant_emails, f"expected {email} in {participant_emails}")
            )

        # Timesheet entries exist
        for email, hours, label in [
            (emp_email_14a, 8, "timesheet_a_8h"),
            (emp_email_14b, 5, "timesheet_b_5h"),
        ]:
            resp_e = client.get("employee", params={"email": email, "count": 1})
            emps = resp_e.json().get("values", [])
            if not emps:
                checks.append((label, False, f"employee {email} not found"))
                continue
            emp_id = emps[0]["id"]
            resp_t = client.get(
                "timesheet/entry",
                params={
                    "employeeId": emp_id,
                    "dateFrom": "2020-01-01",
                    "dateTo": "2030-01-01",
                    "count": 50,
                },
            )
            entries = resp_t.json().get("values", [])
            has_hours = any(e.get("hours") == hours for e in entries)
            checks.append(
                (label, has_hours, f"entries hours: {[e.get('hours') for e in entries]}")
            )
        return checks

    # --- Task 13.1: Create Customer from PDF attachment (structured file) ---
    cust_name_13 = f"Nordlys Digital {uid} AS"
    org_nr_13 = "6" + uid[:8].translate(str.maketrans("abcdef", "123456"))
    cust_address_13 = "Havnegata 12"
    cust_postal_13 = "7010"
    cust_city_13 = "Trondheim"

    pdf_lines_13 = [
        "TILBUDSBREV",
        "",
        f"Kundenavn: {cust_name_13}",
        f"Organisasjonsnummer: {org_nr_13}",
        f"Adresse: {cust_address_13}",
        f"Postnummer: {cust_postal_13}",
        f"Poststed: {cust_city_13}",
        "",
        "Vi bekrefter herved tilbudet for IT-konsulenttjenester.",
    ]
    pdf_bytes_13 = _make_pdf(pdf_lines_13)
    pdf_b64_13 = base64.b64encode(pdf_bytes_13).decode()

    def verify_task_13(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get(
            "customer",
            params={"customerName": cust_name_13, "count": 5, "fields": "id,postalAddress(*)"},
        )
        custs = resp.json().get("values", [])
        if not custs:
            return [("customer_exists", False, f"No customer '{cust_name_13}'")]
        cust = custs[0]
        addr = cust.get("postalAddress", {}) or {}
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust['id']}"),
            (
                "address_line",
                addr.get("addressLine1") == cust_address_13,
                f"expected {cust_address_13!r}, got {addr.get('addressLine1')!r}",
            ),
            (
                "postal_code",
                addr.get("postalCode") == cust_postal_13,
                f"expected {cust_postal_13!r}, got {addr.get('postalCode')!r}",
            ),
            (
                "city",
                addr.get("city") == cust_city_13,
                f"expected {cust_city_13!r}, got {addr.get('city')!r}",
            ),
        ]
        return checks

    # --- Task 16.1: Expense Reclassification by Account Lookup (German) ---
    reclass_date = "2026-04-10"
    reclass_amount_5000 = 32000.0
    reclass_amount_6000 = 18500.0

    def setup_task_16(client: httpx.Client) -> None:
        # Get account IDs for 5000 and 6000
        resp = client.get("ledger/account", params={"number": "5000,6000,1920", "count": 5})
        resp.raise_for_status()
        accts = {a["number"]: a["id"] for a in resp.json()["values"]}
        acct_5000 = accts[5000]
        acct_6000 = accts[6000]
        acct_1920 = accts[1920]

        # Create a voucher with a posting to 5000
        resp = client.post(
            "ledger/voucher",
            json={
                "date": reclass_date,
                "description": f"Lønnskostnad april {uid}",
                "postings": [
                    {
                        "date": reclass_date,
                        "account": {"id": acct_5000},
                        "vatType": {"id": 0},
                        "amountGross": reclass_amount_5000,
                        "amountGrossCurrency": reclass_amount_5000,
                        "row": 1,
                    },
                    {
                        "date": reclass_date,
                        "account": {"id": acct_1920},
                        "vatType": {"id": 0},
                        "amountGross": -reclass_amount_5000,
                        "amountGrossCurrency": -reclass_amount_5000,
                        "row": 2,
                    },
                ],
            },
        )
        resp.raise_for_status()
        print(f"  [setup] Created voucher 5000 ({reclass_amount_5000} NOK)")

        # Create a voucher with a posting to 6000
        resp = client.post(
            "ledger/voucher",
            json={
                "date": reclass_date,
                "description": f"Avskrivning april {uid}",
                "postings": [
                    {
                        "date": reclass_date,
                        "account": {"id": acct_6000},
                        "vatType": {"id": 0},
                        "amountGross": reclass_amount_6000,
                        "amountGrossCurrency": reclass_amount_6000,
                        "row": 1,
                    },
                    {
                        "date": reclass_date,
                        "account": {"id": acct_1920},
                        "vatType": {"id": 0},
                        "amountGross": -reclass_amount_6000,
                        "amountGrossCurrency": -reclass_amount_6000,
                        "row": 2,
                    },
                ],
            },
        )
        resp.raise_for_status()
        print(f"  [setup] Created voucher 6000 ({reclass_amount_6000} NOK)")

    def verify_task_16(client: httpx.Client) -> list[VerifyCheck]:
        tomorrow = (
            datetime.strptime(reclass_date, "%Y-%m-%d").replace(tzinfo=UTC)
            + timedelta(days=1)
        ).date()
        resp = client.get(
            "ledger/voucher",
            params={
                "dateFrom": reclass_date,
                "dateTo": tomorrow.isoformat(),
                "count": 200,
            },
        )
        vouchers = resp.json().get("values", [])

        # Find a reclassification voucher that debits 5000 and credits 6000
        # (i.e. moves the 6000 amount into 5000)
        target = None
        for v in vouchers:
            postings = v.get("postings", [])
            if postings and not postings[0].get("account", {}).get("number"):
                resp2 = client.get(
                    f"ledger/voucher/{v['id']}",
                    params={"fields": "postings(*,account(*))"},
                )
                postings = resp2.json().get("value", {}).get("postings", [])
            acct_numbers = {p.get("account", {}).get("number", 0) for p in postings}
            # Reclassification: touches both 5000 and 6000, but NOT 1920
            if 5000 in acct_numbers and 6000 in acct_numbers and 1920 not in acct_numbers:
                target = v
                target["_postings"] = postings
                break

        if not target:
            return [
                (
                    "reclass_voucher_exists",
                    False,
                    f"No voucher with both 5000 and 6000 (without 1920) among {len(vouchers)} vouchers",
                ),
            ]

        postings = target["_postings"]
        debit_5000 = sum(
            p.get("amountGross", 0)
            for p in postings
            if p.get("account", {}).get("number") == 5000 and p.get("amountGross", 0) > 0
        )
        credit_6000 = sum(
            p.get("amountGross", 0)
            for p in postings
            if p.get("account", {}).get("number") == 6000 and p.get("amountGross", 0) < 0
        )
        debit_total = sum(p.get("amountGross", 0) for p in postings if p.get("amountGross", 0) > 0)
        credit_total = sum(p.get("amountGross", 0) for p in postings if p.get("amountGross", 0) < 0)

        checks: list[VerifyCheck] = [
            ("reclass_voucher_exists", True, f"id={target['id']}"),
            (
                "correct_amount",
                abs(debit_5000 - reclass_amount_6000) < 0.01,
                f"debit 5000={debit_5000}, expected {reclass_amount_6000}",
            ),
            (
                "correct_credit",
                abs(credit_6000 + reclass_amount_6000) < 0.01,
                f"credit 6000={credit_6000}, expected -{reclass_amount_6000}",
            ),
            (
                "balanced",
                abs(debit_total + credit_total) < 0.01,
                f"debit={debit_total} credit={credit_total}",
            ),
        ]
        return checks

    # --- Task 15.1: Monthly Closing — Combined Voucher (Portuguese) ---
    def setup_task_15(client: httpx.Client) -> None:
        pass  # no setup needed — uses standard chart of accounts

    def verify_task_15(client: httpx.Client) -> list[VerifyCheck]:
        today = datetime.now(tz=UTC).date()
        tomorrow = today + timedelta(days=1)
        resp = client.get(
            "ledger/voucher",
            params={
                "dateFrom": today.isoformat(),
                "dateTo": tomorrow.isoformat(),
                "count": 200,
            },
        )
        vouchers = resp.json().get("values", [])
        # Find voucher(s) that touch both 5000-series (salary) and 6010 (depreciation)
        matching_vouchers: list[dict] = []
        for v in vouchers:
            postings = v.get("postings", [])
            if postings and not postings[0].get("account", {}).get("number"):
                resp2 = client.get(
                    f"ledger/voucher/{v['id']}",
                    params={"fields": "postings(*,account(*))"},
                )
                postings = resp2.json().get("value", {}).get("postings", [])
            acct_numbers = {p.get("account", {}).get("number", 0) for p in postings}
            has_salary = any(5000 <= n < 6000 for n in acct_numbers)
            has_depreciation = 6010 in acct_numbers
            has_accrual = 7700 in acct_numbers or 1710 in acct_numbers
            if has_salary and has_depreciation:
                matching_vouchers.append(v)
                # Re-attach expanded postings for checks
                v["_postings"] = postings

        if not matching_vouchers:
            # Check if entries exist spread across multiple vouchers (the bad pattern)
            salary_vouchers = []
            depreciation_vouchers = []
            for v in vouchers:
                postings = v.get("postings", [])
                if postings and not postings[0].get("account", {}).get("number"):
                    resp2 = client.get(
                        f"ledger/voucher/{v['id']}",
                        params={"fields": "postings(*,account(*))"},
                    )
                    postings = resp2.json().get("value", {}).get("postings", [])
                acct_numbers = {p.get("account", {}).get("number", 0) for p in postings}
                if any(5000 <= n < 6000 for n in acct_numbers):
                    salary_vouchers.append(v)
                if 6010 in acct_numbers:
                    depreciation_vouchers.append(v)
            if salary_vouchers and depreciation_vouchers:
                return [
                    (
                        "combined_voucher",
                        False,
                        f"Entries exist but in separate vouchers (salary={len(salary_vouchers)}, "
                        f"depreciation={len(depreciation_vouchers)}). Should be combined into one.",
                    ),
                ]
            return [
                (
                    "combined_voucher",
                    False,
                    f"No voucher with both salary and depreciation postings among {len(vouchers)} vouchers",
                ),
            ]

        target = matching_vouchers[0]
        postings = target["_postings"]
        acct_numbers = {p.get("account", {}).get("number", 0) for p in postings}
        has_salary = any(5000 <= n < 6000 for n in acct_numbers)
        has_depreciation = 6010 in acct_numbers

        debit_total = sum(p.get("amountGross", 0) for p in postings if p.get("amountGross", 0) > 0)
        credit_total = sum(p.get("amountGross", 0) for p in postings if p.get("amountGross", 0) < 0)

        checks: list[VerifyCheck] = [
            ("combined_voucher", True, f"id={target['id']}, {len(postings)} postings"),
            ("has_salary_posting", has_salary, f"accounts: {sorted(acct_numbers)}"),
            ("has_depreciation_posting", has_depreciation, f"accounts: {sorted(acct_numbers)}"),
            (
                "balanced",
                abs(debit_total + credit_total) < 0.01,
                f"debit={debit_total} credit={credit_total}",
            ),
        ]
        return checks

    # --- Task 17.1: Custom Accounting Dimension + Voucher (French) ---
    dim_name_17 = f"Kostsenter {uid}"
    dim_val_a_17 = f"Økonomi {uid}"
    dim_val_b_17 = f"IT {uid}"

    def verify_task_17(client: httpx.Client) -> list[VerifyCheck]:
        # Check dimension name exists
        resp = client.get("ledger/accountingDimensionName")
        dim_names = resp.json().get("values", [])
        dim_match = [d for d in dim_names if d.get("dimensionName") == dim_name_17]
        if not dim_match:
            return [("dimension_name_exists", False, f"No dimension named '{dim_name_17}'")]
        dim = dim_match[0]
        dim_index = dim["dimensionIndex"]

        # Check dimension values exist
        resp = client.get(
            "ledger/accountingDimensionValue",
            params={"dimensionIndex": dim_index, "count": 50},
        )
        vals = resp.json().get("values", [])
        val_names = {v.get("displayName") for v in vals}
        has_val_a = dim_val_a_17 in val_names
        has_val_b = dim_val_b_17 in val_names
        val_b_id = next((v["id"] for v in vals if v.get("displayName") == dim_val_b_17), None)

        checks: list[VerifyCheck] = [
            ("dimension_name_exists", True, f"id={dim['id']} index={dim_index}"),
            ("value_okonomi", has_val_a, f"values: {sorted(val_names)}"),
            ("value_it", has_val_b, f"values: {sorted(val_names)}"),
        ]

        # Check voucher on account 6340 with dimension value "IT"
        today = datetime.now(tz=UTC).date()
        tomorrow = today + timedelta(days=1)
        resp = client.get(
            "ledger/voucher",
            params={"dateFrom": today.isoformat(), "dateTo": tomorrow.isoformat(), "count": 200},
        )
        vouchers = resp.json().get("values", [])
        dim_field = f"freeAccountingDimension{dim_index}"
        target = None
        for v in vouchers:
            postings = v.get("postings", [])
            if postings and not postings[0].get("account", {}).get("number"):
                resp2 = client.get(
                    f"ledger/voucher/{v['id']}",
                    params={"fields": f"postings(*,account(number),{dim_field}(*))"},
                )
                postings = resp2.json().get("value", {}).get("postings", [])
            for p in postings:
                acct_num = p.get("account", {}).get("number", 0)
                dim_val = p.get(dim_field)
                if acct_num == 6340 and dim_val and dim_val.get("id") == val_b_id:
                    target = v
                    target["_postings"] = postings
                    break
            if target:
                break

        if not target:
            checks.append(
                ("voucher_with_dimension", False, f"No voucher on 6340 with {dim_field}=IT among {len(vouchers)} vouchers")
            )
            return checks

        postings = target["_postings"]
        debit_6340 = sum(
            p.get("amountGross", 0)
            for p in postings
            if p.get("account", {}).get("number") == 6340 and p.get("amountGross", 0) > 0
        )
        checks.extend([
            ("voucher_with_dimension", True, f"id={target['id']}"),
            (
                "correct_amount",
                abs(debit_6340 - 5050) < 0.01,
                f"debit 6340={debit_6340}, expected 5050",
            ),
        ])
        return checks

    # --- Task 18.1: Receipt Expense as Voucher (German) ---
    dept_name_18 = f"Markedsføring {uid}"
    receipt_amount_18 = 4950.0
    receipt_vat_18 = 990.0  # 25% VAT included in 4950
    receipt_ex_vat_18 = 3960.0

    def setup_task_18(client: httpx.Client) -> None:
        resp = client.post("department", json={"name": dept_name_18})
        resp.raise_for_status()
        print(f"  [setup] Created department '{dept_name_18}' (id={resp.json()['value']['id']})")

    receipt_pdf_18 = _make_pdf([
        "Elkjøp Bergen",
        "Dato: 30.03.2026",
        "",
        "Tastatur Logitech MX Keys     4 950,00 NOK",
        "  herav MVA 25%                  990,00 NOK",
        "",
        "Betalt med kort",
    ])

    def verify_task_18(client: httpx.Client) -> list[VerifyCheck]:
        checks: list[VerifyCheck] = []

        # Check that NO travel expense was created with this department
        resp = client.get("department", params={"name": dept_name_18, "count": 5})
        depts = resp.json().get("values", [])
        if not depts:
            return [("department_found", False, f"Department '{dept_name_18}' not found")]
        dept_id = depts[0]["id"]

        resp = client.get(
            "travelExpense",
            params={"departmentId": dept_id, "count": 50},
        )
        travel_exps = resp.json().get("values", [])
        checks.append(
            (
                "no_travel_expense",
                len(travel_exps) == 0,
                f"Found {len(travel_exps)} travel expenses — keyboard purchase should be a voucher, not travel",
            )
        )

        # Check that a voucher was created with a posting to an expense account (6xxx range)
        # in this department. Receipt date may be in the future, so use a wide range.
        today = datetime.now(tz=UTC).date()
        resp = client.get(
            "ledger/posting",
            params={
                "dateFrom": (today - timedelta(days=30)).isoformat(),
                "dateTo": (today + timedelta(days=60)).isoformat(),
                "departmentId": dept_id,
                "count": 100,
                "fields": "id,account(number,name),amountGross,amountGrossCurrency,voucher(id,description)",
            },
        )
        postings = resp.json().get("values", [])
        # Look for a debit to a 6xxx expense account
        expense_postings = [
            p for p in postings
            if 6000 <= (p.get("account", {}).get("number") or 0) < 7000
            and (p.get("amountGross") or 0) > 0
        ]
        if not expense_postings:
            checks.append(
                ("voucher_expense_posting", False, "No debit posting to 6xxx expense account in department")
            )
            return checks

        checks.append(("voucher_expense_posting", True, f"Found {len(expense_postings)} expense posting(s)"))

        # Check amount — the gross amount on the expense posting should relate to receipt total
        # With 25% VAT, the gross amount could be 4950 (inc VAT) or 3960 (ex VAT) depending on
        # whether the account is VAT-locked. Either is acceptable as long as it's consistent.
        best_posting = expense_postings[0]
        gross = best_posting.get("amountGross", 0)
        amount_ok = abs(gross - receipt_amount_18) < 1.0 or abs(gross - receipt_ex_vat_18) < 1.0
        checks.append(
            (
                "correct_amount",
                amount_ok,
                f"expense posting amountGross={gross}, expected ~{receipt_amount_18} (incl VAT) or ~{receipt_ex_vat_18} (excl VAT)",
            )
        )

        return checks

    # --- Task 20.1: Supplier Invoice Voucher (Spanish) ---
    supplier_name_20 = f"Kontorrekvisita {uid} AS"
    supplier_invoice_date_20 = "2026-03-21"
    supplier_invoice_gross_20 = 12500.0  # 10000 net + 2500 VAT (25%)
    supplier_invoice_net_20 = 10000.0

    def setup_task_20(client: httpx.Client) -> None:
        resp = client.post("supplier", json={"name": supplier_name_20})
        resp.raise_for_status()
        sup_id = resp.json()["value"]["id"]
        print(f"  [setup] Created supplier '{supplier_name_20}' (id={sup_id})")

    def verify_task_20(client: httpx.Client) -> list[VerifyCheck]:
        today = datetime.now(tz=UTC).date()
        tomorrow = today + timedelta(days=1)
        resp = client.get(
            "ledger/voucher",
            params={
                "dateFrom": supplier_invoice_date_20,
                "dateTo": tomorrow.isoformat(),
                "count": 200,
            },
        )
        vouchers = resp.json().get("values", [])

        # Find voucher with a posting to account 2400
        target = None
        target_postings: list[dict] = []
        for v in vouchers:
            postings = v.get("postings", [])
            if postings and not postings[0].get("account", {}).get("number"):
                resp2 = client.get(
                    f"ledger/voucher/{v['id']}",
                    params={"fields": "postings(*,account(*),supplier(*))"},
                )
                postings = resp2.json().get("value", {}).get("postings", [])
            acct_numbers = {p.get("account", {}).get("number", 0) for p in postings}
            if 2400 in acct_numbers and 6540 in acct_numbers:
                target = v
                target_postings = postings
                break

        if not target:
            return [
                ("voucher_exists", False, f"No voucher with 2400+6540 postings among {len(vouchers)} vouchers"),
            ]

        checks: list[VerifyCheck] = [
            ("voucher_exists", True, f"id={target['id']}"),
        ]

        # Check that 2400 posting has supplier linked
        posting_2400 = [p for p in target_postings if p.get("account", {}).get("number") == 2400]
        if posting_2400:
            sup = posting_2400[0].get("supplier")
            has_supplier = sup is not None and sup.get("id") is not None
            checks.append(
                ("supplier_on_2400", has_supplier, f"supplier={sup}"),
            )
        else:
            checks.append(("supplier_on_2400", False, "No posting to account 2400"))

        # Check amounts are reasonable (gross on 2400, net on 6540)
        posting_6540 = [p for p in target_postings if p.get("account", {}).get("number") == 6540]
        if posting_6540:
            debit_amount = posting_6540[0].get("amountGross", 0)
            checks.append(
                (
                    "expense_amount",
                    abs(debit_amount - supplier_invoice_gross_20) < 1.0
                    or abs(debit_amount - supplier_invoice_net_20) < 1.0,
                    f"amountGross={debit_amount}, expected net={supplier_invoice_net_20} or gross={supplier_invoice_gross_20}",
                ),
            )

        # Check balanced (use net amount — amountGross doesn't balance when auto-VAT postings exist)
        net_total = sum(p.get("amount", 0) for p in target_postings)
        checks.append(
            ("balanced", abs(net_total) < 0.01, f"net_total={net_total}"),
        )

        return checks

    # --- Task 19.1: Reverse Invoice Payment (Norwegian) ---
    cust_name_19 = f"Snøhetta {uid} AS"
    invoice_amount_19 = 49600.0

    def setup_task_19(client: httpx.Client) -> None:
        _ensure_bank_account(client)
        resp = client.post("customer", json={"name": cust_name_19})
        resp.raise_for_status()
        cust_id = resp.json()["value"]["id"]
        print(f"  [setup] Created customer '{cust_name_19}' (id={cust_id})")

        resp = client.post(
            "invoice",
            json={
                "invoiceDate": "2026-03-15",
                "invoiceDueDate": "2026-04-15",
                "customer": {"id": cust_id},
                "orders": [
                    {
                        "orderDate": "2026-03-15",
                        "deliveryDate": "2026-03-15",
                        "customer": {"id": cust_id},
                        "orderLines": [
                            {
                                "description": "Systemutvikling",
                                "count": 1,
                                "unitPriceExcludingVatCurrency": invoice_amount_19,
                            },
                        ],
                    },
                ],
            },
        )
        resp.raise_for_status()
        inv_id = resp.json()["value"]["id"]
        print(f"  [setup] Created invoice (id={inv_id})")

        # Get payment type
        resp = client.get("invoice/paymentType", params={"count": 5})
        resp.raise_for_status()
        pay_types = resp.json()["values"]
        pay_type_id = pay_types[0]["id"]

        # Register payment
        resp = client.put(
            f"invoice/{inv_id}/:payment",
            params={
                "paymentDate": "2026-03-20",
                "paymentTypeId": pay_type_id,
                "paidAmount": invoice_amount_19,
            },
        )
        resp.raise_for_status()
        outstanding = resp.json()["value"]["amountOutstanding"]
        print(f"  [setup] Registered payment on invoice {inv_id} (outstanding={outstanding})")

    def verify_task_19(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("customer", params={"customerName": cust_name_19, "count": 5})
        custs = resp.json().get("values", [])
        if not custs:
            return [("customer_exists", False, f"No customer '{cust_name_19}'")]
        cust_id = custs[0]["id"]

        resp = client.get(
            "invoice",
            params={
                "customerId": cust_id,
                "invoiceDateFrom": "2020-01-01",
                "invoiceDateTo": "2030-01-01",
                "count": 10,
            },
        )
        invoices = resp.json().get("values", [])
        if not invoices:
            return [
                ("customer_exists", True, f"id={cust_id}"),
                ("invoice_exists", False, "No invoice found"),
            ]

        # Find the original invoice (not a credit note)
        original = [i for i in invoices if not i.get("isCreditNote", False)]
        if not original:
            return [
                ("customer_exists", True, f"id={cust_id}"),
                ("invoice_exists", False, "No non-credit-note invoice found"),
            ]
        inv = original[0]
        outstanding = inv.get("amountOutstanding", 0)

        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust_id}"),
            ("invoice_exists", True, f"id={inv['id']}"),
        ]

        # The payment should be reversed, so amountOutstanding should be back to the invoice amount
        checks.append(
            (
                "payment_reversed",
                outstanding > 0,
                f"amountOutstanding={outstanding}, expected >0 (payment reversed)",
            )
        )
        checks.append(
            (
                "amount_restored",
                abs(outstanding - invoice_amount_19) < 1.0,
                f"amountOutstanding={outstanding}, expected ~{invoice_amount_19}",
            )
        )

        # Ensure no credit note was created (wrong approach)
        credit_notes = [i for i in invoices if i.get("isCreditNote", False)]
        checks.append(
            (
                "no_credit_note",
                len(credit_notes) == 0,
                f"Found {len(credit_notes)} credit notes — should reverse payment, not create credit note",
            )
        )

        return checks

    return [
        {
            "name": "1.1 Create Employee (Norwegian)",
            "prompt": (
                f"Opprett en ansatt ved navn {emp_first} {emp_last}, "
                f"født 15. mars 1988, e-post {emp_email}, startdato 1. april 2026, "
                f'avdeling "{dept_name_1}".'
            ),
            "setup": setup_task_1,
            "verify": verify_task_1,
            # GET department + POST employee (inline employment) = 2
            "optimal": 2,
            "best": 2,
        },
        {
            "name": "2.1 Create Invoice (English)",
            "prompt": (
                f"Create an invoice dated March 25, 2026 due April 25, 2026 for customer "
                f'"{cust_name_2}" with 3 units of product "{prod_name_2}" at 2500 kr each.'
            ),
            "setup": setup_task_2,
            "verify": verify_task_2,
            # GET customer + GET product + POST invoice (inline order+lines) = 3
            "optimal": 3,
            "best": 3,
        },
        {
            "name": "3.1 Update Customer Address (French)",
            "prompt": (
                f'Le client "{cust_name_3}" a déménagé. '
                f"Mettez à jour son adresse à Storgata 45, 0182 Oslo."
            ),
            "setup": setup_task_3,
            "verify": verify_task_3,
            # GET customer (returns address id/version) + PUT customer = 2
            "optimal": 2,
            "best": 3,
        },
        {
            "name": "4.1 Delete Department (German)",
            "prompt": f'Bitte löschen Sie die Abteilung "{dept_name_4}".',
            "setup": setup_task_4,
            "verify": verify_task_4,
            # GET department + DELETE department = 2
            "optimal": 2,
            "best": 2,
        },
        {
            "name": "5.1 Full Invoice with Payment (Spanish)",
            "prompt": (
                f'Cree un cliente "{cust_name_5}", un producto "{prod_name_5}" a 1200 kr, '
                f"y genere una factura con fecha 20 de marzo de 2026, vencimiento 20 de abril de 2026, "
                f"con 10 unidades del producto. Luego registre el pago completo con fecha 20 de marzo de 2026."
            ),
            "verify": verify_task_5,
            # POST customer + POST product + GET paymentType + POST invoice + PUT payment = 5
            "optimal": 5,
            "best": 5,
        },
        {
            "name": "6.1 Create Project (English)",
            "prompt": (
                f'Create the project "{proj_name_6}" linked to the customer "{cust_name_6}". '
                f"Add {emp_first_6} {emp_last_6} ({emp_email_6}) as a participant on the project."
            ),
            "setup": setup_task_6,
            "verify": verify_task_6,
            # GET customer + GET employee + GET /token/session/>whoAmI + POST project (inline participants) = 4
            "optimal": 4,
            "best": 4,
        },
        {
            "name": "7.1 Run Payroll via Voucher (English)",
            "prompt": (
                f"Run payroll for {emp_first_7} {emp_last_7} ({emp_email_7}) for this month. "
                f"The base salary is 34950 NOK. Add a one-time bonus of 15450 NOK on top of the base salary. "
                f"Link the expense to the employee in the system. "
                f"If the salary API is unavailable, you can use manual vouchers on salary accounts "
                f"(5000-series) to record the payroll expense."
            ),
            "setup": setup_task_7,
            "verify": verify_task_7,
            # GET employee + GET ledger/account (salary+payable combined) + POST ledger/voucher = 3
            "optimal": 3,
            "best": 3,
        },
        {
            "name": "8.1 Timesheet + Project Invoice (Spanish)",
            "prompt": (
                f"Registre 11 horas para {emp_first_8} {emp_last_8} ({emp_email_8}) "
                f'en la actividad "{activity_name_8}" del proyecto "{proj_name_8}" '
                f"para {cust_name_8}. Tarifa por hora: 1850 NOK/h. "
                f"Genere una factura de proyecto al cliente basada en las horas registradas."
            ),
            "setup": setup_task_8,
            "verify": verify_task_8,
            # GET employee + GET project(fields=projectActivities(*),projectHourlyRates(*))
            # + PUT project/hourlyRates + POST timesheet/entry + POST invoice (inline order) = 5
            "optimal": 5,
            "best": 5,
        },
        {
            "name": "9.1 Multi-line Invoice Org#+Prod# (Norwegian)",
            "prompt": (
                f"Opprett en faktura til kunden {cust_name_9} (org.nr {org_nr_9}) med tre produktlinjer: "
                f"{prod_name_9a} ({prod_num_9a}) til 5400 kr med 25 % MVA, "
                f"{prod_name_9b} ({prod_num_9b}) til 6850 kr med 15 % MVA (næringsmiddel), og "
                f"{prod_name_9c} ({prod_num_9c}) til 13750 kr med 0 % MVA (avgiftsfri). "
                f"Fakturadato 1. april 2026, forfall 1. mai 2026."
            ),
            "setup": setup_task_9,
            "verify": verify_task_9,
            # GET /customer?organizationNumber + GET /product?productNumber (batch) + POST /invoice = 3
            "optimal": 3,
            "best": 3,
        },
        {
            "name": "10.1 Fixed-price Project Invoice (German)",
            "prompt": (
                f'Legen Sie einen Festpreis von 473250 NOK für das Projekt "{proj_name_10}" fest. '
                f"Stellen Sie dem Kunden 25 % des Festpreises als Meilensteinzahlung in Rechnung. "
                f"Fakturadatum: 1. April 2026, Fälligkeitsdatum: 1. Mai 2026."
            ),
            "setup": setup_task_10,
            "verify": verify_task_10,
            # GET /project?name + PUT /project (fixedprice) + POST /invoice (inline order+line, no product needed) = 3
            "optimal": 3,
            "best": 3,
        },
        {
            "name": "11.1 Order→Invoice+Payment (German)",
            "prompt": (
                f"Der Kunde {cust_name_11} (Org.-Nr. {org_nr_11}) hat einen bestehenden Auftrag. "
                f"Wandeln Sie diesen Auftrag in eine Rechnung um (Rechnungsdatum: 1. April 2026) "
                f"und registrieren Sie die vollständige Zahlung am 1. April 2026."
            ),
            "setup": setup_task_11,
            "verify": verify_task_11,
            # GET /customer?orgNr + GET /order?customerId
            # + PUT /order/:invoice + GET /invoice/paymentType + PUT /invoice/:payment = 5
            "optimal": 5,
            "best": 5,
        },
        {
            "name": "12.1 Credit Note (French)",
            "prompt": (
                f'Créez une note de crédit pour la facture du client "{cust_name_12}" '
                f"avec la date du 21 mars 2026 et le commentaire « Annulation de service »."
            ),
            "setup": setup_task_12,
            "verify": verify_task_12,
            # GET /customer + GET /invoice + PUT /invoice/:createCreditNote = 3
            "optimal": 3,
            "best": 3,
        },
        {
            "name": "13.1 Customer from PDF (structured file)",
            "prompt": (
                "The attached PDF is an offer letter (tilbudsbrev). "
                "Extract the customer details from the PDF and create the customer in Tripletex "
                "with the name, organization number, and postal address from the document."
            ),
            "files": [
                {
                    "filename": "tilbudsbrev.pdf",
                    "content_base64": pdf_b64_13,
                    "mime_type": "application/pdf",
                },
            ],
            "verify": verify_task_13,
            # POST /customer = 1
            "optimal": 1,
            "best": 1,
        },
        {
            "name": "14.1 Project + Timesheet 2 Employees (Norwegian)",
            "prompt": (
                f'Opprett prosjektet "{proj_name_14}" (internt). '
                f"Opprett aktiviteten \"{activity_name_14}\" og koble den til prosjektet. "
                f"Legg til {emp_first_14a} {emp_last_14a} ({emp_email_14a}) og "
                f"{emp_first_14b} {emp_last_14b} ({emp_email_14b}) som deltakere. "
                f"Registrer 8 timer for {emp_first_14a} og 5 timer for {emp_first_14b} "
                f"den 15. april 2026 på aktiviteten."
            ),
            "setup": setup_task_14,
            "verify": verify_task_14,
            # GET employee(email1) + GET employee(email2) + GET whoAmI
            # + POST activity + POST project(inline participants+activity)
            # + POST timesheet/entry(A) + POST timesheet/entry(B) = 7
            "optimal": 7,
            "best": 7,
        },
        {
            "name": "15.1 Monthly Closing — Combined Voucher (Portuguese)",
            "prompt": (
                "Realize o fecho mensal de março 2026 com as seguintes três operações num único lançamento manual "
                "com data de hoje:\n"
                "1. Reversão de acréscimo: débito conta 7700, crédito conta 1710, valor 5000 NOK\n"
                "2. Depreciação: débito conta 6010, crédito conta 1710, valor 2656.25 NOK\n"
                "3. Provisão salarial: débito conta 5000, crédito conta 2900, valor 50000 NOK\n"
                "Todas as operações devem ser registadas num único voucher."
            ),
            "setup": setup_task_15,
            "verify": verify_task_15,
            # GET /ledger/account?number=7700,1710,6010,5000,2900 + POST /ledger/voucher = 2
            "optimal": 2,
            "best": 2,
        },
        {
            "name": "16.1 Expense Reclassification from Postings (German)",
            "prompt": (
                f"Am {reclass_date} wurden Buchungen auf Konto 5000 (Lönn til ansatte) und "
                f"Konto 6000 (Avskrivning) verbucht. "
                f"Ermitteln Sie den Gesamtbetrag der Buchungen auf Konto 6000 an diesem Datum "
                f"und erstellen Sie einen Umgliederungsbeleg (Datum {reclass_date}), "
                f"der diesen Betrag von Konto 6000 auf Konto 5000 umbucht."
            ),
            "setup": setup_task_16,
            "verify": verify_task_16,
            # GET /ledger/account?number=5000,6000 (1)
            # + GET /ledger/posting?accountId=6000_id (1)
            # + POST /ledger/voucher (1) = 3
            "optimal": 3,
            "best": 3,
        },
        {
            "name": "17.1 Accounting Dimension + Voucher (French)",
            "prompt": (
                f'Créez une dimension comptable personnalisée "{dim_name_17}" avec les valeurs '
                f'"{dim_val_a_17}" et "{dim_val_b_17}". '
                f"Puis comptabilisez une pièce sur le compte 6340 pour 5050 NOK, "
                f'liée à la valeur de dimension "{dim_val_b_17}".'
            ),
            "verify": verify_task_17,
            # POST /ledger/accountingDimensionName (1)
            # + POST /ledger/accountingDimensionValue x2 (2)
            # + GET /ledger/account?number=6340,1920 (1)
            # + POST /ledger/voucher (1) = 5
            "optimal": 5,
        },
        {
            "name": "18.1 Receipt Expense as Voucher (German)",
            "prompt": (
                f"Wir benötigen die Tastatur-Ausgabe aus dieser Quittung in der Abteilung "
                f'"{dept_name_18}". '
                f"Verwenden Sie das richtige Aufwandskonto und stellen Sie die korrekte "
                f"MwSt.-Behandlung sicher."
            ),
            "files": [
                {
                    "filename": "kvittering_tastatur.pdf",
                    "content_base64": base64.b64encode(receipt_pdf_18).decode(),
                },
            ],
            "setup": setup_task_18,
            "verify": verify_task_18,
            # GET /department (1) + GET /ledger/account (1) + POST /ledger/voucher (1) = 3
            "optimal": 3,
        },
        {
            "name": "19.1 Reverse Invoice Payment (Norwegian)",
            "prompt": (
                f'Betalingen fra {cust_name_19} for fakturaen "Systemutvikling" '
                f"({invoice_amount_19:.0f} kr ekskl. MVA) ble returnert av banken. "
                f"Reverser betalingen slik at fakturaen igjen viser utestående beløp."
            ),
            "setup": setup_task_19,
            "verify": verify_task_19,
            # GET /customer + GET /invoice + GET /ledger/posting (find payment voucher)
            # + PUT /ledger/voucher/:reverse = 4
            "optimal": 4,
        },
        {
            "name": "20.1 Supplier Invoice Voucher (Spanish)",
            "prompt": (
                f'Registre una factura del proveedor "{supplier_name_20}" por un total de '
                f"{supplier_invoice_gross_20:.0f} NOK (IVA incluido al 25%). "
                f"Fecha: {supplier_invoice_date_20}. "
                f"Débito la cuenta de gastos 6540 (inventar/utstyr) con el importe neto, "
                f"y acredite la cuenta 2400 (leverandørgjeld) con el importe bruto. "
                f"Asegúrese de vincular la línea del proveedor correctamente."
            ),
            "setup": setup_task_20,
            "verify": verify_task_20,
            # GET /supplier?name=... (1) + GET /ledger/account?number=6540,2400 (1)
            # + POST /ledger/voucher (1) = 3
            "optimal": 3,
            "best": 3,
        },
    ]


def _build_local_system_prompt() -> str:
    """Assemble the same system prompt used by solve.py, adapted for CLI tools."""
    skills_dir = _PROJECT_ROOT / "skills"
    task_prompt = (_PROJECT_ROOT / "prompt.md").read_text()
    scoring = (skills_dir / "scoring.md").read_text()

    available_skills = sorted(p.stem for p in skills_dir.glob("*.md") if p.name != "scoring.md")

    skill_index = """\
## Available Skill References

Call `read_skill(skill_name)` to read the full reference for an entity type. \
You MUST read the relevant skill before making POST/PUT calls. \
This tool is free and does not count toward your efficiency score.

| Skill | Covers |
|-------|--------|
| _general | API patterns: references, responses, versioning, inline creation, error translations, lookups |
| customer | Customer CRUD, address nested updates |
| department | Department CRUD (no dependencies) |
| employee | Employee + Employment, userType, department req |
| invoice | Invoice + Orders + OrderLines, payment/credit note (query params), bank account prereq |
| ledger | Ledger accounts, postings, vouchers, VAT codes, currency |
| product | Product CRUD, VAT gotcha, unique names |
| project | Project CRUD, projectManager, inline participants/activities, hourly rates |
| activity | Activity CRUD, activityType, linking to projects |
| timesheet | Timesheet entry (hours registration), allocated hours, month/week approval |
| travel | Travel expenses, costs, mileage, per diem, accommodation, rate categories |"""

    cli_path = _HERE / "tripletex_cli.py"

    tool_instructions = f"""\
## Tools — CLI Interface

You interact with the Tripletex API via a CLI tool. Run commands using Bash.
The CLI tool is at: {cli_path}

### Commands:
- `uv run python {cli_path} get <endpoint> [--params '{{"key":"val"}}']` — GET request
- `uv run python {cli_path} post <endpoint> --data '{{"key":"val"}}'` — POST request
- `uv run python {cli_path} put <endpoint> --data '{{"key":"val"}}'` — PUT request
- `uv run python {cli_path} delete <endpoint>` — DELETE request
- `uv run python {cli_path} read-skill <skill_name>` — Read a skill reference (free, doesn't count)
- `uv run python {cli_path} review-plan '<your plan>' --domains <domain> [<domain> ...]` — Review your planned API calls for optimality (free, doesn't count). Pick domain(s) matching the API endpoints in your plan:
  - `employee` — /employee, /department, /employment
  - `invoice` — /invoice, /order, /product, /customer
  - `ledger` — /ledger, /voucher, /account, /posting
  - `project` — /project, /activity, /timesheet
  - `travel` — /travelExpense, /mileage, /perDiem, /accommodation

Available skills: {', '.join(available_skills)}

All commands return JSON. On HTTP errors, the JSON contains an "error" key.
Endpoints should NOT include /v2/ prefix (it's added automatically).

### Important
- ONLY use the CLI tool above to interact with the Tripletex API.
- Do NOT use curl, httpx, or any other HTTP client directly.
- Do NOT read, grep, or inspect source files — the CLI tool works, just use it.
- Do NOT debug or inspect log files — they are managed automatically.
- Focus exclusively on solving the task. No exploration, no file inspection.
"""

    # Replace the tool section in the task prompt since we use CLI instead
    # The original prompt.md references tripletex_get etc. — replace with CLI reference
    adapted_prompt = task_prompt.replace(
        "## Tools\n\nYou have four tools for interacting with the Tripletex API.",
        "## Tools\n\nSee the CLI Interface section above for how to interact with the API.",
    )

    return f"{skill_index}\n\n{tool_instructions}\n\n{adapted_prompt}\n\n{scoring}"


def run_task_server(task: SyntheticTask, tx_client: httpx.Client) -> dict:
    """Run a task against the HTTP solve server."""
    bearer_token = os.environ["BEARER_TOKEN"]

    payload: dict[str, Any] = {
        "prompt": task["prompt"],
        "tripletex_credentials": {
            "base_url": TRIPLETEX_BASE_URL,
            "session_token": TRIPLETEX_SESSION_TOKEN,
        },
    }
    if task.get("files"):
        payload["files"] = task["files"]

    start = time.time()
    resp = httpx.post(
        f"{BASE}/solve",
        headers={"Authorization": f"Bearer {bearer_token}"},
        json=payload,
        timeout=300,
    )
    elapsed = time.time() - start

    body = resp.json() if resp.status_code == 200 else {}
    api_calls = body.get("api_calls")
    errors = body.get("errors")

    result = {
        "name": task["name"],
        "status_code": resp.status_code,
        "elapsed_s": round(elapsed, 1),
        "api_calls": api_calls,
        "errors": errors,
        "optimal": task.get("optimal"),
        "best": task.get("best"),
        "response": body if resp.status_code == 200 else resp.text,
    }
    calls_str = f"calls={api_calls} err={errors}" if api_calls is not None else ""
    print(f"Status: {resp.status_code} | Time: {elapsed:.1f}s | {calls_str}")
    return result


def run_task_local(task: SyntheticTask, system_prompt: str, model: str | None) -> dict:
    """Run a task via a local Claude Code subagent."""
    # Create a temp file for the call log
    log_fd, log_path = tempfile.mkstemp(suffix=".jsonl", prefix="tx_calls_")
    os.close(log_fd)

    env = {
        **os.environ,
        "TRIPLETEX_BASE_URL": TRIPLETEX_BASE_URL,
        "TRIPLETEX_SESSION_TOKEN": TRIPLETEX_SESSION_TOKEN,
        "CALL_LOG_FILE": log_path,
    }
    # Prevent "nested session" detection when invoked from within Claude Code
    env.pop("CLAUDECODE", None)

    # Save file attachments to temp files so the CLI agent can read them
    temp_file_paths: list[Path] = []
    file_instructions = ""
    if task.get("files"):
        tmpdir = Path(tempfile.mkdtemp(prefix="tx_files_"))
        for f in task["files"]:
            if isinstance(f, dict):
                filename = f["filename"]
                data = base64.b64decode(f["content_base64"])
            else:
                filename = "attachment.bin"
                data = base64.b64decode(f)
            fpath = tmpdir / filename
            fpath.write_bytes(data)
            temp_file_paths.append(fpath)
            print(f"  [setup] Saved file attachment: {fpath}")
        paths_str = ", ".join(str(p) for p in temp_file_paths)
        file_instructions = (
            f"\n\n## Attached Files\n\n"
            f"The following files are attached to this task. "
            f"Use the Read tool to read them: {paths_str}"
        )

    prompt = f"## Task\n\n{task['prompt']}{file_instructions}"

    cmd = [
        "claude",
        "-p",
        prompt,
        "--system-prompt",
        system_prompt,
        "--tools",
        "Bash",
        "Read",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    cmd.extend(["--model", model or "sonnet"])

    stderr_path = log_path + ".stderr"
    stderr_fh = Path(stderr_path).open("w")  # noqa: SIM115
    start = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=_PROJECT_ROOT.parent,
            stdout=subprocess.PIPE,
            stderr=stderr_fh,
            text=True,
        )

        # Stream stdout line-by-line and collect messages
        messages: list[dict] = []
        assert proc.stdout is not None
        for raw_line in iter(proc.stdout.readline, ""):
            line = raw_line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                messages.append(msg)
                # Print streaming progress for key message types
                msg_type = msg.get("type", "")
                if msg_type == "assistant" and "message" in msg:
                    content = msg["message"].get("content", [])
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "text":
                            text = block["text"]
                            preview = text[:200] + ("..." if len(text) > 200 else "")
                            print(f"  [assistant] {preview}", flush=True)
                        elif block.get("type") == "tool_use":
                            tool = block.get("name", "?")
                            inp = json.dumps(block.get("input", {}))[:120]
                            print(f"  [tool_use] {tool} {inp}", flush=True)
                elif msg_type == "user":
                    # Tool results come back as type=user
                    content = msg.get("message", {}).get("content", [])
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            snippet = str(block.get("content", ""))[:120]
                            print(f"  [tool_result] {snippet}", flush=True)
                elif msg_type == "result":
                    print(f"  [result] is_error={msg.get('is_error', False)}", flush=True)
            except json.JSONDecodeError:
                print(f"  [raw] {line[:200]}", flush=True)

        stderr_fh.close()
        stderr_output = Path(stderr_path).read_text()
        proc.wait(timeout=300)
        elapsed = time.time() - start

        # Parse call log — only count actual Tripletex API calls, not read-skill
        log_file = Path(log_path)
        # JSONL format: one JSON object per line (safe under concurrent writes)
        calls = (
            [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
            if log_file.exists() and log_file.stat().st_size > 0
            else []
        )
        counted_methods = {"GET", "POST", "PUT", "DELETE"}
        free_methods = {"READ_SKILL", "REVIEW_PLAN"}
        for c in calls:
            method = c["method"]
            if method not in counted_methods and method not in free_methods:
                raise ValueError(
                    f"Unknown call method in log: {method!r}. "
                    "Add it to counted_methods or free_methods.",
                )
        api_calls = sum(1 for c in calls if c["method"] in counted_methods)
        errors = sum(1 for c in calls if c.get("is_error"))

        status_code = 200 if proc.returncode == 0 else 500

        result = {
            "name": task["name"],
            "status_code": status_code,
            "elapsed_s": round(elapsed, 1),
            "api_calls": api_calls,
            "errors": errors,
            "optimal": task.get("optimal"),
            "best": task.get("best"),
            "response": messages,
            "calls_detail": calls,
        }
        if proc.returncode != 0 and stderr_output:
            result["stderr"] = stderr_output[:2000]

        calls_str = f"calls={api_calls} err={errors}"
        if proc.returncode != 0:
            error_msg = stderr_output.strip() or ""
            if not error_msg:
                for m in messages:
                    if m.get("type") == "result" and m.get("is_error"):
                        error_msg = m.get("result", "unknown error")
                        break
            print(f"FAIL: {proc.returncode} | Time: {elapsed:.1f}s | {error_msg}")
        else:
            print(f"Exit: {proc.returncode} | Time: {elapsed:.1f}s | {calls_str}")

        # Print call log summary
        counted = [c for c in calls if c["method"] in counted_methods]
        if counted:
            print("  [calls]")
            for i, c in enumerate(counted, 1):
                ep = c.get("endpoint", "")
                method = c["method"]
                status = c.get("status_code", "")
                err = " ERROR" if c.get("is_error") else ""
                params = c.get("params", {})
                data = c.get("data_summary", "")
                detail = ""
                if params:
                    detail = " " + "&".join(f"{k}={v}" for k, v in params.items())
                elif data:
                    detail = f" {data[:80]}"
                print(f"    {i}. {method} /{ep} → {status}{err}{detail}")

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        proc.kill()
        print(f"TIMEOUT after {elapsed:.1f}s")
        result = {
            "name": task["name"],
            "status_code": 504,
            "elapsed_s": round(elapsed, 1),
            "api_calls": None,
            "errors": None,
            "optimal": task.get("optimal"),
            "best": task.get("best"),
            "response": "timeout",
        }
    finally:
        stderr_fh.close()
        Path(stderr_path).unlink(missing_ok=True)
        Path(log_path).unlink(missing_ok=True)
        for fpath in temp_file_paths:
            fpath.unlink(missing_ok=True)
        if temp_file_paths:
            temp_file_paths[0].parent.rmdir()

    return result


def run_task(
    task: SyntheticTask,
    tx_client: httpx.Client,
    *,
    local: bool = False,
    system_prompt: str | None = None,
    model: str | None = None,
) -> dict:
    print(f"\n{'='*60}")
    print(f"TASK: {task['name']}")
    print(f"{'='*60}")
    print(f"Prompt: {task['prompt'][:120]}...")

    # Run setup if present
    setup_fn: Callable[[httpx.Client], None] | None = task.get("setup")
    if setup_fn is not None:
        setup_fn(tx_client)

    if local:
        assert system_prompt is not None
        result = run_task_local(task, system_prompt, model)
    else:
        result = run_task_server(task, tx_client)

    # Run verification
    verify_fn: Callable[[httpx.Client], list[VerifyCheck]] | None = task.get("verify")
    if verify_fn is not None and result["status_code"] in (200, 500):
        try:
            checks = verify_fn(tx_client)
            verification = _verify_checks(checks)
            result["verification"] = verification
            status = "PASS" if verification["all_passed"] else "FAIL"
            print(
                f"  [verify] {status} ({verification['passed']}/{verification['total']})",
                flush=True,
            )
            for line in verification["failures"]:
                print(f"  {line}", flush=True)
        except Exception as e:  # noqa: BLE001
            result["verification"] = {"all_passed": False, "error": str(e)}
            print(f"  [verify] ERROR: {e}", flush=True)

    return result


def print_summary(results: list[dict]) -> None:
    print(f"\n{'='*72}")
    print("SUMMARY")
    print(f"{'='*72}")
    print(
        f"  {'Task':<40} {'Status':<6} {'Verify':<8} {'Calls':>5} {'Err':>4} {'Best':>5} {'Opt':>4} {'Time':>7}",
    )
    print(f"  {'-'*40} {'-'*6} {'-'*8} {'-'*5} {'-'*4} {'-'*5} {'-'*4} {'-'*7}")
    for r in results:
        st = "OK" if r["status_code"] == 200 else "FAIL"
        v = r.get("verification", {})
        if v.get("error"):
            vfy = "ERROR"
        elif v.get("all_passed") or v:
            vfy = f"{v['passed']}/{v['total']}"
        else:
            vfy = "-"
        calls = r["api_calls"] if r.get("api_calls") is not None else "-"
        errs = r["errors"] if r.get("errors") is not None else "-"
        best = r.get("best") if r.get("best") is not None else "-"
        opt = r.get("optimal") if r.get("optimal") is not None else "-"
        print(
            f"  {r['name']:<40} {st:<6} {vfy:<8} {calls:>5} {errs:>4} {best:>5} {opt:>4} {r['elapsed_s']:>6.1f}s",
        )

    ok = sum(1 for r in results if r["status_code"] == 200)
    verified = sum(1 for r in results if r.get("verification", {}).get("all_passed"))
    total = len(results)
    total_calls = sum(r.get("api_calls") or 0 for r in results)
    total_errors = sum(r.get("errors") or 0 for r in results)
    total_optimal = sum(r.get("optimal") or 0 for r in results)
    print(
        f"\n  {ok}/{total} tasks completed | {verified}/{total} verified | calls={total_calls} errors={total_errors} optimal={total_optimal}",
    )


def save_results(results: list[dict]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"synthetic_results_{ts}.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {path}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run synthetic tasks")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local Claude Code subagent instead of HTTP server",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model override for --local mode (e.g. sonnet, opus, haiku)",
    )
    parser.add_argument(
        "--tasks",
        type=str,
        default=None,
        help="Comma-separated task indices to run (e.g. '1,3,5'), 1-indexed",
    )
    args = parser.parse_args()

    all_tasks = build_tasks()

    if args.tasks:
        indices = [int(x.strip()) - 1 for x in args.tasks.split(",")]
        tasks = [all_tasks[i] for i in indices]
    else:
        tasks = all_tasks

    tx_client = _tripletex_client()

    # Ensure sandbox company is VAT-registered (required for tasks with non-zero VAT)
    vat_resp = tx_client.get("ledger/vatSettings")
    vat_resp.raise_for_status()
    vat_data = vat_resp.json()["value"]
    if vat_data["vatRegistrationStatus"] != "VAT_REGISTERED":
        vat_data["vatRegistrationStatus"] = "VAT_REGISTERED"
        tx_client.put("ledger/vatSettings", json=vat_data).raise_for_status()
        print("[setup] Enabled VAT registration on sandbox company")

    system_prompt = _build_local_system_prompt() if args.local else None
    if args.local:
        print("Running in LOCAL mode (Claude Code subagent)")
        if args.model:
            print(f"Model: {args.model}")

    results = []
    for task in tasks:
        result = run_task(
            task,
            tx_client,
            local=args.local,
            system_prompt=system_prompt,
            model=args.model,
        )
        results.append(result)

    print_summary(results)
    save_results(results)
