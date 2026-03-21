# Unresolved Issues

Issues observed during testing that need further investigation.

## Salary provision amount not in task prompt — agent invented 50000 NOK

**Found in:** Log `downloaded-logs-20260321-140912.json`, Task 1 — Monthly closing (Portuguese)
**Observed:** Task prompt says "provisão salarial (débito conta de despesas salariais 5000, crédito conta de salários acumulados 2900)" — specifies account numbers but no amount. Agent posted 50000 NOK with no basis in the prompt.
**Expected:** Needs investigation — the amount has no source in the task input.
**Raw evidence:**
```
Task prompt: "Registe também uma provisão salarial (débito conta de despesas salariais 5000, crédito conta de salários acumulados 2900)."
13:04:42 POST ledger/voucher data={"postings": [{"account": {"id": 462973964}, "amountGross": 50000.0}, {"account": {"id": 462973874}, "amountGross": -50000.0}]} -> 201
```

## Error correction task timed out — throttling and rate limits consumed most of the 300s budget

**Found in:** Log `downloaded-logs-20260321-142609.json`, Task 1 — Spanish ledger error correction
**Observed:** Task required finding and correcting 4 ledger errors. Agent completed 3 of 4 corrections before hitting the 300s timeout at 334s elapsed. Breakdown: input token throttling added ~100s of delay (1s + 11s + 11.8s + 13.9s + 15s×6), three Anthropic 429 retries added ~87s (6s + 29s + 52s). Total waiting: ~187s out of 334s. The actual API calls and LLM processing took ~147s. 15 API calls made, 2 errors.
**Expected:** Task should complete within 300s. The throttling delays alone (100s) plus rate limit retries (87s) consumed 56% of the time budget.
**Raw evidence:**
```
13:18:23 POST /solve (task start)
13:18:26 Throttling 1.0s for 502 input tokens
13:18:30 Throttling 11.0s for 5504 input tokens
13:18:52 Throttling 11.8s for 5876 input tokens
13:19:20 Throttling 13.9s for 6961 input tokens
13:19:39–13:22:25 Throttling 15.0s × 6 iterations
13:20:45 429 retry 6s, 13:21:39 429 retry 29s, 13:22:40 429 retry 52s
13:23:57 Aborting: task exceeded 300s (334.0s elapsed)
TASK SUMMARY | api_calls=15 | errors=2
```

## SPECULATIVE: Tax provision computed from adjustment totals, not actual P&L result

**Found in:** Log `downloaded-logs-20260321-145622.json`, Task 2 — Annual closing 2025 (Spanish)
**Speculative — logs don't show agent reasoning or response bodies.**
**Observed:** Agent posted tax provision of 42620.63 NOK (22% of 193730.15). The number 193730.15 exactly equals the sum of all adjustment amounts: 39944.44 (IT depreciation) + 113200.0 (office machines) + 17335.71 (software) + 23250.0 (prepaid reversal). The task says "22% del resultado imponible" (22% of taxable income), which should be the full P&L result for 2025, not just the year-end adjustments. The agent never fetched any P&L/result data from the API.
**Why speculative:** Cannot see the agent's reasoning. The exact match to the sum of adjustments is suspicious but not proof — the agent may have had another basis for this number that isn't visible in the logs.
**Raw evidence:**
```
No GET for P&L or result balance anywhere in the task.
13:54:44 POST ledger/voucher data={"description": "Skatteavsetning 2025 - 22% av skattepliktig resultat (193730.15 NOK)", "postings": [{"account": {"id": 463726234}, "amountGross": 42620.63}, {"account": {"id": 463704764}, "amountGross": -42620.63}]} -> 201
39944.44 + 113200.0 + 17335.71 + 23250.0 = 193730.15
```

## project/subcontract: `company` field does not map to internal `customerId`

**Found in:** Sandbox investigation of the `displayName` issue (2026-03-21)
**Observed:** `POST /project/subcontract` with `displayName`, `name`, `project`, and `company` (valid customer/supplier ID that resolves on `/company/{id}`) still returns 422: `"Internt felt (customerId): Feltet må fylles ut."`. Tested with: plain customer IDs, supplier IDs, customer+supplier combo IDs, own company ID (108120146), projects with and without customers. The `company` field is accepted (no "field does not exist" error) but never populates the internal `customerId`.
**Expected:** Setting `company` with a valid entity ID should populate `customerId` and allow subcontract creation.
**Raw evidence:**
```
POST /project/subcontract {"project":{"id":402004568},"company":{"id":108264576},"displayName":"Test Sub","name":"Test Sub"} -> 422 "Internt felt (customerId): Feltet må fylles ut."
POST /project/subcontract {"project":{"id":402004568},"company":{"id":108344050},"displayName":"Test Sub","name":"Test Sub"} -> 422 (same — supplier ID)
POST /project/subcontract {"project":{"id":402004568},"company":{"id":108120146},"displayName":"Test Sub","name":"Test Sub"} -> 422 (same — own company)
GET /company/108264576 -> 200 (ID is valid Company entity)
```

## Task 20.1: first POST attempt fails with 422 before succeeding on retry

**Found in:** Task 20.1 — Supplier Invoice Voucher (Spanish), `synthetic_results_20260321_173254.json`
**Observed:** Agent's first POST used `amountGross=10000` (net) on the expense line with `vatType: {id: 1}` (25% VAT). Tripletex rejected with 422 because user-posted lines must balance on gross. Agent retried with `amountGross=12500` (gross including VAT) and succeeded. The final voucher is correct: 6540 gross=12500 (net=10000), 2400 gross=-12500, auto-VAT 2710 gross=2500. Net balances to zero.
**Expected:** Agent should get it right on the first attempt — `amountGross` means gross (VAT-inclusive) for lines with a vatType.
**Raw evidence:**
```
POST /ledger/voucher (attempt 1, amountGross=10000 on 6540) → 422
POST /ledger/voucher (attempt 2, amountGross=12500 on 6540) → 201 ✓
Voucher: row1 6540 gross=12500 net=10000 | row2 2400 gross=-12500 | row0 2710 gross=2500 (auto)
```

## Task 5.1: Invoice POST missing deliveryDate on first attempt

**Found in:** `synthetic_results_20260321_182643.json`, Task 5.1 — Full Invoice with Payment (Spanish)
**Observed:** Agent's first POST /invoice omitted `deliveryDate` on the inline order. Tripletex returned 422: `orders.deliveryDate: Kan ikke være null`. Agent retried with `deliveryDate` included and succeeded. Cost 1 extra API call (6 total vs 5 optimal).
**Expected:** Agent should include `deliveryDate` on the first attempt — the invoice skill documents it as required.
**Raw evidence:**
```
POST /invoice (attempt 1, no deliveryDate on order) → 422 "orders.deliveryDate: Kan ikke være null"
POST /invoice (attempt 2, with deliveryDate) → 201 ✓
```

## Task 12.1: review-plan timed out after 60s

**Found in:** `synthetic_results_20260321_182643.json`, Task 12.1 — Credit Note (French)
**Observed:** Agent called review-plan which timed out after 60s. May indicate the plan text was malformed or the review LLM call was slow.
**Raw evidence:**
```
review-plan → {"error": "Review timed out after 60.0s"}
```

## Task 12.1: Agent used `name` instead of `customerName` param

**Found in:** `synthetic_results_20260321_182643.json`, Task 12.1 — Credit Note (French)
**Observed:** Agent called `GET /customer --params '{"name": "..."}'` which was caught by the client-side guardrail (ToolError, not an API call). Agent corrected to `customerName` on the next attempt. The customer skill documents the correct param name.
**Expected:** Agent should use `customerName` on the first attempt — this is documented in the customer skill.
**Raw evidence:**
```
GET /customer params={"name": "Bordeaux Consulting d2ea65c8 SAS"} → ToolError "Wrong param 'name' for /customer. Use 'customerName' instead."
GET /customer params={"customerName": "Bordeaux Consulting d2ea65c8 SAS"} → 200 ✓
```
