# Unresolved Issues

Issues observed during testing that need further investigation.

## project/subcontract: unknown required field `displayName`

**Found in:** Log `downloaded-logs-20260321-131222.json`, Task 3 — Full project cycle (supplier cost for Nordhav AS)
**Observed:** `POST project/subcontract` failed twice with HTTP 422: `displayName: "Kan ikke vaere null."`. First attempt included `company`, `name`, `budgetExpensesCurrency`. Second dropped `company`, added `budgetNetAmountCurrency`. Neither included `displayName`. Agent fell back to `POST project/orderline` which succeeded.
**Expected:** The agent should either know `displayName` is required, or know the correct endpoint for registering supplier costs on a project.
**Raw evidence:**
```
12:10:01 POST project/subcontract data={"project": {"id": ...}, "company": {"id": ...}, "name": "Nordhav AS leverandorkostnad", "budgetExpensesCurrency": 95050}
12:10:16 POST project/subcontract -> HTTP 422: displayName: "Kan ikke vaere null."
12:10:45 POST project/subcontract data={"project": {"id": ...}, "name": "...", "budgetExpensesCurrency": 95050, "budgetNetAmountCurrency": 95050}
12:10:50 POST project/subcontract -> HTTP 422: displayName: "Kan ikke vaere null."
12:11:32 POST project/orderline data={...} -> 201 (fallback)
```

## Unnecessary whoAmI and department calls in project task

**Found in:** Log `downloaded-logs-20260321-131222.json`, Task 3 — Full project cycle
**Observed:** Agent fired 7 parallel GETs in its first API round, including `GET token/session/>whoAmI` and `GET department params={'count': 5}`. Neither result was used in any subsequent call. The task specified employees by email and no department assignment was needed.
**Expected:** These calls should only be made when the task requires current-user info or department assignment.
**Raw evidence:**
```
12:08:05 GET token/session/>whoAmI params=None
12:08:29 GET department params={'count': 5}
```
Neither endpoint's response was referenced in any subsequent POST/PUT.
**Review-plan called:** yes
**Review-plan caught it:** no

## Possible duplicate customer creation (Nordhav AS)

**Found in:** Log `downloaded-logs-20260321-131222.json`, Task 3 — Full project cycle
**Observed:** Agent did `GET customer params={'organizationNumber': '957929974'}` which returned HTTP 200, then later did `POST customer data={name: "Nordhav AS", organizationNumber: "957929974", isSupplier: true}` which returned 201. If the GET returned a match, the POST created a duplicate. Log does not show response bodies so the GET result content is unknown.
**Expected:** If the customer already exists, the agent should reuse the existing ID.
**Raw evidence:**
```
12:08:13 GET customer params={'organizationNumber': '957929974'} -> 200
12:08:43 POST customer data={"name": "Nordhav AS", "organizationNumber": "957929974", "isSupplier": true} -> 201
```

## Agent hallucinates invalid fields/params on ledger/posting

**Found in:** Log `downloaded-logs-20260321-135344.json`, Task 1 — German expense analysis task
**Observed:** Agent tried `GET ledger/posting` with `fields=count,total,values(...)` (400 — `total` invalid), then `fields=count,values(...)` (400 — `values` invalid), then `accountId` as a query param (404 x2). Four wasted API calls before falling back to unfiltered requests.
**Expected:** The agent should use only valid PostingDTO fields in the `fields` filter and valid query parameters for the endpoint.
**Raw evidence:**
```
12:46:58 GET ledger/posting params={'dateFrom': '2026-01-01', 'dateTo': '2026-03-01', 'count': 1000, 'fields': 'count,total,values(date,account(id,number,name),amountGross)'} -> HTTP 400: "Illegal field in fields filter: total"
12:47:02 GET ledger/posting params={'dateFrom': '2026-01-01', 'dateTo': '2026-03-01', 'count': 1000, 'fields': 'count,values(date,account(id,number,name),amountGross)'} -> HTTP 400: "Illegal field in fields filter: values"
12:49:32 GET ledger/posting params={'dateFrom': '2026-01-01', 'dateTo': '2026-02-01', 'count': 100, 'accountId': '462754854,...'} -> HTTP 404
12:49:33 GET ledger/posting params={'dateFrom': '2026-02-01', 'dateTo': '2026-03-01', 'count': 100, 'accountId': '462754854,...'} -> HTTP 404
```

## Rate limit crash — unhandled 429 kills task with HTTP 500

**Found in:** Log `downloaded-logs-20260321-135344.json`, Task 1 — German expense analysis task
**Observed:** After iteration 10, the Anthropic SDK hit 3 consecutive 429s in rapid succession. Earlier in the task, single 429s were retried successfully (23s, 31s, 44s, 53s backoffs), but the final burst exhausted retries and the `RateLimitError` propagated uncaught through `solve.py`, returning HTTP 500 to the caller. The task had been running for ~4 minutes and had accumulated ~35k input tokens per request.
**Expected:** The task should not crash with HTTP 500 when hitting Anthropic rate limits.
**Raw evidence:**
```
12:50:23 HTTP Request: POST https://api.anthropic.com/v1/messages?beta=true "HTTP/1.1 429 Too Many Requests"
12:50:23 Retrying request to /v1/messages?beta=true in 0.461190 seconds
12:50:23 HTTP Request: POST https://api.anthropic.com/v1/messages?beta=true "HTTP/1.1 429 Too Many Requests"
12:50:23 Retrying request to /v1/messages?beta=true in 0.816074 seconds
12:50:24 HTTP Request: POST https://api.anthropic.com/v1/messages?beta=true "HTTP/1.1 429 Too Many Requests"
anthropic.RateLimitError: ... rate limit of 30,000 input tokens per minute
```

## Inefficient ledger analysis: fetched all postings instead of using aggregated endpoints

**Found in:** Log `downloaded-logs-20260321-135344.json`, Task 1 — German expense analysis task
**Observed:** To find the three expense accounts with the largest cost increase Jan→Feb, the agent fetched all `ledger/posting` entries (count=1000) and attempted to compute per-account totals manually. This produced a large response payload (~20k+ tokens in iteration 7 context), contributing to the rate limit that eventually crashed the task.
**Expected:** The agent should use more efficient approaches such as `resultBudget` or aggregated ledger endpoints to get per-account totals directly, avoiding large posting dumps.
**Raw evidence:**
```
12:47:04 GET ledger/posting params={'dateFrom': '2026-01-01', 'dateTo': '2026-03-01', 'count': 1000} -> 200
# Context grew from 11k to 20k input tokens after this response
12:50:22 GET ledger/posting params={'dateFrom': '2026-01-01', 'dateTo': '2026-02-01', 'count': 100} -> 200
12:50:22 GET ledger/posting params={'dateFrom': '2026-02-01', 'dateTo': '2026-03-01', 'count': 100} -> 200
```
**Review-plan called:** yes
**Review-plan caught it:** no
