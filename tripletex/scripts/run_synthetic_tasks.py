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
import json
import os
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
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
        resp = client.get("employee", params={"firstName": emp_first, "lastName": emp_last, "count": 5, "fields": "id,email,employments(*)"})
        vals = resp.json().get("values", [])
        if not vals:
            return [("employee_exists", False, f"No employee found with name {emp_first} {emp_last}")]
        emp = vals[0]
        checks: list[VerifyCheck] = [
            ("employee_exists", True, f"id={emp['id']}"),
            ("email", emp.get("email") == emp_email, f"expected {emp_email}, got {emp.get('email')}"),
        ]
        # Check employment start date
        emps = emp.get("employments", [])
        has_start = any(e.get("startDate") == "2026-04-01" for e in emps)
        checks.append(("employment_start_date", has_start, f"expected 2026-04-01 in employments"))
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
        resp = client.get("invoice", params={"customerId": cust_id, "invoiceDateFrom": "2020-01-01", "invoiceDateTo": "2030-01-01", "count": 5})
        invoices = resp.json().get("values", [])
        if not invoices:
            return [("customer_exists", True, ""), ("invoice_exists", False, "No invoice found for customer")]
        inv = invoices[0]
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust_id}"),
            ("invoice_exists", True, f"id={inv['id']}"),
            ("invoice_date", inv.get("invoiceDate") == "2026-03-25", f"expected 2026-03-25, got {inv.get('invoiceDate')}"),
        ]
        # Check order lines via the order
        orders = inv.get("orders", [])
        if orders:
            order_id = orders[0].get("id")
            resp = client.get(f"order/{order_id}", params={"fields": "orderLines(*)"})
            order = resp.json().get("value", {})
            lines = order.get("orderLines", [])
            has_3_units = any(l.get("count") == 3 for l in lines)
            checks.append(("order_line_count_3", has_3_units, f"lines: {[(l.get('count'), l.get('unitPriceExcludingVatCurrency')) for l in lines]}"))
        return checks

    # --- Task 3.1: Update Customer Address (needs pre-created customer) ---
    cust_name_3 = f"Fjord Consulting {uid}"

    def setup_task_3(client: httpx.Client) -> None:
        resp = client.post("customer", json={"name": cust_name_3})
        resp.raise_for_status()
        print(f"  [setup] Created customer '{cust_name_3}' (id={resp.json()['value']['id']})")

    def verify_task_3(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("customer", params={"customerName": cust_name_3, "count": 5, "fields": "id,postalAddress(*)"})
        custs = resp.json().get("values", [])
        if not custs:
            return [("customer_exists", False, f"No customer '{cust_name_3}'")]
        cust = custs[0]
        addr = cust.get("postalAddress", {}) or {}
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust['id']}"),
            ("address_line", addr.get("addressLine1") == "Storgata 45", f"expected 'Storgata 45', got {addr.get('addressLine1')!r}"),
            ("postal_code", addr.get("postalCode") == "0182", f"expected '0182', got {addr.get('postalCode')!r}"),
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
        return [("department_deleted", len(vals) == 0, f"found {len(vals)} departments named '{dept_name_4}'")]

    # --- Task 5.1: Full Invoice with Payment ---
    cust_name_5 = f"Nordic Solutions {uid} AS"
    prod_name_5 = f"Consultoría TI {uid}"

    def verify_task_5(client: httpx.Client) -> list[VerifyCheck]:
        resp = client.get("customer", params={"customerName": cust_name_5, "count": 5})
        custs = resp.json().get("values", [])
        if not custs:
            return [("customer_exists", False, f"No customer '{cust_name_5}'")]
        cust_id = custs[0]["id"]
        resp = client.get("invoice", params={"customerId": cust_id, "invoiceDateFrom": "2020-01-01", "invoiceDateTo": "2030-01-01", "count": 5})
        invoices = resp.json().get("values", [])
        if not invoices:
            return [("customer_exists", True, ""), ("invoice_exists", False, "No invoice found")]
        inv = invoices[0]
        amount = inv.get("amountExcludingVat")
        expected_amount = 10 * 1200  # 10 units * 1200 kr (excl. VAT)
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust_id}"),
            ("invoice_exists", True, f"id={inv['id']}"),
            ("amount_excl_vat", amount == expected_amount, f"expected {expected_amount}, got {amount}"),
            ("is_paid", inv.get("amountOutstanding") == 0, f"outstanding={inv.get('amountOutstanding')}"),
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
        checks.append(("customer_linked", proj_cust.get("id") == expected_cust_id,
                        f"expected cust_id={expected_cust_id}, got {proj_cust.get('id')}"))
        # Check participant
        resp3 = client.get(f"project/{proj['id']}", params={"fields": "participants(employee(*))"})
        participants = resp3.json().get("value", {}).get("participants", [])
        participant_emails = [p.get("employee", {}).get("email") for p in participants]
        checks.append(("participant_added", emp_email_6 in participant_emails,
                        f"expected {emp_email_6} in {participant_emails}"))
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
        from datetime import timedelta
        today = datetime.now(tz=UTC).date()
        tomorrow = today + timedelta(days=1)
        # Find recent vouchers — dateFrom/dateTo required, dateTo is exclusive
        resp = client.get("ledger/voucher", params={
            "dateFrom": today.isoformat(), "dateTo": tomorrow.isoformat(), "count": 200,
        })
        vouchers = resp.json().get("values", [])
        # Find a voucher that has postings on a salary account (5000-series)
        target_voucher = None
        target_postings = None
        for v in vouchers:
            postings = v.get("postings", [])
            # Postings in listing are stubs — fetch with expanded fields
            if postings and not postings[0].get("account", {}).get("number"):
                resp2 = client.get(f"ledger/voucher/{v['id']}", params={"fields": "postings(*,account(*))"})
                postings = resp2.json().get("value", {}).get("postings", [])
            for p in postings:
                acct_num = p.get("account", {}).get("number", 0)
                if 5000 <= acct_num < 6000 and abs(p.get("amountGross", 0)) > 0:
                    target_voucher = v
                    target_postings = postings
                    break
            if target_voucher:
                break
        if not target_voucher:
            return [("voucher_exists", False, f"No voucher with 5000-series account found among {len(vouchers)} vouchers on {today}")]
        debit_total = sum(p.get("amountGross", 0) for p in target_postings if p.get("amountGross", 0) > 0)
        credit_total = sum(p.get("amountGross", 0) for p in target_postings if p.get("amountGross", 0) < 0)
        checks: list[VerifyCheck] = [
            ("voucher_exists", True, f"id={target_voucher['id']}"),
            ("debit_amount", debit_total == total_salary, f"expected {total_salary}, got {debit_total}"),
            ("credit_amount", credit_total == -total_salary, f"expected {-total_salary}, got {credit_total}"),
            ("balanced", debit_total + credit_total == 0, f"debit={debit_total} credit={credit_total}"),
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
        resp = client.get("employee", params={"firstName": emp_first_8, "lastName": emp_last_8, "count": 5})
        emps = resp.json().get("values", [])
        if not emps:
            return [("employee_found", False, f"No employee '{emp_first_8} {emp_last_8}'")]
        emp_id = emps[0]["id"]
        resp = client.get("timesheet/entry", params={"employeeId": emp_id, "dateFrom": "2020-01-01", "dateTo": "2030-01-01", "count": 50})
        entries = resp.json().get("values", [])
        has_11h = any(e.get("hours") == 11 for e in entries)
        checks.append(("timesheet_11h", has_11h, f"entries hours: {[e.get('hours') for e in entries]}"))
        # Check invoice for customer
        resp = client.get("customer", params={"customerName": cust_name_8, "count": 5})
        custs = resp.json().get("values", [])
        if custs:
            cust_id = custs[0]["id"]
            resp = client.get("invoice", params={"customerId": cust_id, "invoiceDateFrom": "2020-01-01", "invoiceDateTo": "2030-01-01", "count": 5})
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
        resp = client.get("invoice", params={"customerId": cust_id, "invoiceDateFrom": "2020-01-01", "invoiceDateTo": "2030-01-01", "count": 5})
        invoices = resp.json().get("values", [])
        if not invoices:
            return [("customer_exists", True, ""), ("invoice_exists", False, "No invoice found")]
        inv = invoices[0]
        checks: list[VerifyCheck] = [
            ("customer_exists", True, f"id={cust_id}"),
            ("invoice_exists", True, f"id={inv['id']}"),
            ("invoice_date", inv.get("invoiceDate") == "2026-04-01", f"got {inv.get('invoiceDate')}"),
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
            ("is_fixed_price", proj.get("isFixedPrice") is True, f"isFixedPrice={proj.get('isFixedPrice')}"),
            ("fixed_price_amount", proj.get("fixedprice") == 473250, f"expected 473250, got {proj.get('fixedprice')}"),
        ]
        # Check milestone invoice (25% of 473250 = 118312.50)
        cust = proj.get("customer", {}) or {}
        if cust.get("id"):
            resp2 = client.get("invoice", params={"customerId": cust["id"], "invoiceDateFrom": "2020-01-01", "invoiceDateTo": "2030-01-01", "count": 5})
            invoices = resp2.json().get("values", [])
            checks.append(("invoice_exists", len(invoices) > 0, f"found {len(invoices)} invoices"))
            if invoices:
                # Check amount is ~25% of 473250
                expected = 473250 * 0.25
                amount = invoices[0].get("amount", 0)
                checks.append(("milestone_amount", abs(amount - expected) < 1, f"expected ~{expected}, got {amount}"))
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
        resp = client.get("order", params={"customerId": cust_id, "orderDateFrom": "2020-01-01", "orderDateTo": "2030-01-01", "count": 5})
        orders = resp.json().get("values", [])
        order_closed = False
        if orders:
            order_closed = orders[0].get("isClosed", False)

        resp = client.get("invoice", params={"customerId": cust_id, "invoiceDateFrom": "2020-01-01", "invoiceDateTo": "2030-01-01", "count": 5})
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
            ("amount_ex_vat", inv.get("amountExcludingVat") == expected_total, f"expected {expected_total}, got {inv.get('amountExcludingVat')}"),
            ("is_paid", inv.get("amountOutstanding") == 0, f"outstanding={inv.get('amountOutstanding')}"),
        ]
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
            # GET project + GET employee + GET activity + POST timesheet/entry
            # + PUT project/hourlyRates + POST invoice (inline order) = 6
            "optimal": 6,
            "best": 6,
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
| _optimality_agent | Generic call-minimization techniques + index of domain-specific optimality skills |
| _optimality_employee | Employee inline patterns (employment + details in 1 call) |
| _optimality_invoice | Invoice inline patterns (orders + lines in 1 call), payment/credit gotchas |
| _optimality_travel | Travel inline patterns (all 4 sub-resources in 1 call), passenger supplement |
| _optimality_project | Project inline patterns (participants + activities in 1 call) |
| _optimality_ledger | Ledger account lookup optimization, payroll vouchers |
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
- `uv run python {cli_path} review-plan '<your plan>'` — Review your planned API calls for optimality (free, doesn't count)

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

    start = time.time()
    resp = httpx.post(
        f"{BASE}/solve",
        headers={"Authorization": f"Bearer {bearer_token}"},
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

    prompt = f"## Task\n\n{task['prompt']}"

    cmd = [
        "claude",
        "-p",
        prompt,
        "--system-prompt",
        system_prompt,
        "--tools",
        "Bash",
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
        proc = subprocess.Popen(  # noqa: S603
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
        _COUNTED_METHODS = {"GET", "POST", "PUT", "DELETE"}
        _FREE_METHODS = {"READ_SKILL", "REVIEW_PLAN"}
        for c in calls:
            method = c["method"]
            if method not in _COUNTED_METHODS and method not in _FREE_METHODS:
                raise ValueError(
                    f"Unknown call method in log: {method!r}. "
                    "Add it to _COUNTED_METHODS or _FREE_METHODS."
                )
        api_calls = sum(1 for c in calls if c["method"] in _COUNTED_METHODS)
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
        counted = [c for c in calls if c["method"] in _COUNTED_METHODS]
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
            print(f"  [verify] {status} ({verification['passed']}/{verification['total']})", flush=True)
            for line in verification["failures"]:
                print(f"  {line}", flush=True)
        except Exception as e:
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
        elif v.get("all_passed"):
            vfy = f"{v['passed']}/{v['total']}"
        elif v:
            vfy = f"{v['passed']}/{v['total']}"
        else:
            vfy = "-"
        calls = r["api_calls"] if r.get("api_calls") is not None else "-"
        errs = r["errors"] if r.get("errors") is not None else "-"
        best = r.get("best", "-")
        opt = r.get("optimal", "-")
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
