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

## Correction voucher with supplier account requires supplier.id — agent didn't know

**Found in:** Log `downloaded-logs-20260321-142609.json`, Task 1 — Spanish ledger error correction
**Observed:** Agent tried to POST a correction voucher for a missing VAT line (account 2710). The voucher included a posting to account 2400 (leverandørgjeld). Tripletex rejected with 422: `"postings.supplier.id": "Leverandør mangler."` — posting lines to supplier-related accounts require a `supplier` object. The agent had no opportunity to retry because the task timed out immediately after.
**Expected:** Agent should know that postings to supplier liability accounts (e.g. 2400) require a `supplier.id` field on the posting.
**Raw evidence:**
```
13:22:40 POST ledger/voucher data={"date": "2026-02-10", "postings": [{"account": {"id": 463200374}, "amountGross": 5475.0, ...}, {"account": {"id": 463200352}, "amountGross": ...}]} -> HTTP 422: "postings.supplier.id": "Leverandør mangler."
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

## Setting unitPriceExcludingVatCurrency on non-chargeable project order line returns 422

**Found in:** Cloud Run log `tripletex-service-00011-2s6` (2026-03-21T13:42:13Z)
**Observed:** Agent did `POST project/orderline` with `unitPriceExcludingVatCurrency` set, but the order line was not marked as chargeable (invoiceable). Tripletex rejected with 422: `"unitPriceExcludingVatCurrency": "Ordrelinjen er ikke fakturerbar."` The `isChargeable` field on `ProjectOrderLine` controls whether a line can carry a selling price. If `isChargeable` is false (or defaults to false), setting a unit selling price is invalid.
**Expected:** Agent should either set `isChargeable: true` when providing a selling price, or omit `unitPriceExcludingVatCurrency` for non-chargeable lines.
**Raw evidence:**
```
13:42:13 POST project/orderline -> HTTP 422: {"validationMessages":[{"field":"unitPriceExcludingVatCurrency","message":"Ordrelinjen er ikke fakturerbar."}]}
```

## Four individual voucher detail GETs instead of batch fetch

**Found in:** Log `downloaded-logs-20260321-142609.json`, Task 1 — Spanish ledger error correction
**Observed:** After identifying 4 suspicious vouchers from postings data, agent fetched each voucher individually with `GET ledger/voucher/{id} params={'fields': 'postings(*,account(*))'}` — 4 sequential GETs. A single `GET ledger/voucher` with an `id` filter or expanding postings in the original voucher list call could reduce this to 1 call.
**Expected:** Batch fetch voucher details in a single call where possible.
**Raw evidence:**
```
13:20:43 GET ledger/voucher/608947983 params={'fields': 'postings(*,account(*))'} -> 200
13:20:44 GET ledger/voucher/608947992 params={'fields': 'postings(*,account(*))'} -> 200
13:20:44 GET ledger/voucher/608948003 params={'fields': 'postings(*,account(*))'} -> 200
13:20:44 GET ledger/voucher/608948009 params={'fields': 'postings(*,account(*))'} -> 200
```
**Review-plan called:** yes
**Review-plan caught it:** no

## Redundant second GET for accounts 1209 and 8700

**Found in:** Log `downloaded-logs-20260321-145622.json`, Task 2 — Annual closing 2025 (Spanish)
**Observed:** Agent fetched all 8 needed accounts in one batch GET (`number=6010,1209,1210,1200,1250,1700,8700,2920`), then did a second GET for just `number=1209,8700`. Since accounts 1209 and 8700 were not in the first result set (agent subsequently created them), the first GET already told the agent they don't exist. The second GET is redundant — 1 wasted call.
**Raw evidence:**
```
13:53:22 GET ledger/account params={'number': '6010,1209,1210,1200,1250,1700,8700,2920', 'count': 20} -> 200
13:53:34 GET ledger/account params={'number': '1209,8700', 'count': 10} -> 200
13:53:49 POST ledger/account data={"number": 1209, ...} -> 201
13:53:50 POST ledger/account data={"number": 8700, ...} -> 201
```

## Prepaid reversal + tax provision as separate vouchers (minor)

**Found in:** Log `downloaded-logs-20260321-145622.json`, Task 2 — Annual closing 2025 (Spanish)
**Observed:** Task explicitly requires "each depreciation as a separate voucher" but says nothing about the prepaid reversal and tax provision. Agent created them as two separate vouchers. These could have been combined into one voucher with 4 posting lines, saving 1 API call.
**Raw evidence:**
```
13:54:44 POST ledger/voucher (prepaid reversal: debit expense, credit 1700) -> 201
13:54:44 POST ledger/voucher (tax provision: debit 8700, credit 2920) -> 201
```
**Review-plan called:** yes
**Review-plan caught it:** no

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

## Prepaid expense reversal used wrong debit account (6010 instead of actual expense account)

**Found in:** Log `downloaded-logs-20260321-145622.json`, Task 2 — Annual closing 2025 (Spanish)
**Observed:** The prepaid reversal voucher debited account ID 463704905 (appears to be 6010, depreciation expense) and credited account ID 463704642 (1700, prepaid expenses). The task says "Revierta gastos prepagados (total 23250 NOK en cuenta 1700)" but does not specify the debit account. The agent defaulted to 6010.
**Expected:** 6010 is a depreciation account and is not a valid debit for a prepaid expense reversal. Norwegian accounting convention (17xx group) requires reversing 1700 against the specific expense account the prepaid relates to (e.g., 6300 for rent, insurance expense for insurance). There is no "default expense account" convention — the agent should inspect the original prepaid entry or invoice description to determine the correct expense account, rather than reusing 6010.
**Raw evidence:**
```
13:54:44 POST ledger/voucher data={"description": "Reversering av forskuddsbetalte kostnader 2025 (konto 1700)", "postings": [{"account": {"id": 463704905}, "amountGross": 23250.0}, {"account": {"id": 463704642}, "amountGross": -23250.0}]} -> 201
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
