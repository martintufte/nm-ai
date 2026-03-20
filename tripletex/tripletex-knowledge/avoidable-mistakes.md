# Avoidable Mistakes

Errors that could be avoided by reading the OpenAPI spec carefully. Documented here as common pitfalls for agent prompting.

## Travel expense dates go in nested `travelDetails`
**Spec says:** TravelExpense has a `travelDetails: TravelDetails` field (schema is correct)
**Mistake:** Putting `departureDate`/`returnDate` at top level. Error: "Feltet eksisterer ikke i objektet."
**Fix:** Nest in `travelDetails`:
```json
{"travelDetails": {"departureDate": "...", "returnDate": "..."}}
```

## Travel cost uses `amountCurrencyIncVat`, NOT `amount`
**Spec says:** Cost has `amountCurrencyIncVat` (writable) and `amount` (read-only on TravelExpense)
**Mistake:** Using `"amount"` in POST body. Error: "Feltet eksisterer ikke i objektet."
**Fix:** Use `"amountCurrencyIncVat": 750.0`

## Invoice payment & credit note use QUERY PARAMS, not body
**Spec says:** Parameters are `in=query` with `required=true` (spec IS correct here, but counterintuitive)
**Mistake:** Sending `{"paymentDate":"...", "paidAmount":...}` as JSON body → 422
**Fix:**
```
PUT /invoice/{id}/:payment?paymentDate=2026-03-20&paymentTypeId=123&paidAmount=1000.0
PUT /invoice/{id}/:createCreditNote?date=2026-03-20&comment=reason
```

## Per diem uses `count` (integer), not date ranges
**Spec says:** `count` is writable; `countFrom`/`countTo` are GET query filter params
**Mistake:** Using `countFrom`/`countTo` in POST body (those are GET query params only)
**Fix:** Use `"count": 2` for number of days

## Base URL already includes `/v2`
**Obvious from:** The sandbox URL `https://kkpqfuj-amager.tripletex.dev/v2`
**Mistake:** Using `{base_url}/v2/employee` → double prefix
**Fix:** Use `{base_url}/employee`

## Passenger supplement is a separate mileage entry, not a boolean
**Spec says:** Rate category 744 is "Bil - passasjertillegg" (a rate type, not a field)
**Mistake:** Adding `"passengerSupplement": true` to a mileage allowance POST. Error: "Verdien er ikke av korrekt type for dette feltet."
**Fix:** Create a SEPARATE mileage allowance entry using rate category 744 for the same km/route.

## GET /invoice requires `invoiceDateFrom` and `invoiceDateTo`
**Spec says:** Both params are `required: true` in the OpenAPI spec
**Mistake:** Omitting date range params when querying invoices. Error: "invoiceDateFrom: Kan ikke være null." / "invoiceDateTo: Kan ikke være null."
**Root cause:** Our `api_reference.md` lists query params as a flat list without indicating which are required. The agent has no way to distinguish required from optional.
**Fix:** Update `api_reference.md` to mark required query params (e.g. `invoiceDateFrom` **(required)**, `invoiceDateTo` **(required)**). Always provide both when listing invoices: `GET /invoice?invoiceDateFrom=2026-01-01&invoiceDateTo=2026-12-31`.

## Employee `startDate` is on Employment, not Employee
**Spec says:** Employee and Employment are separate schemas with separate endpoints
**Mistake:** Including `"startDate"` on POST /employee. Error: "Feltet eksisterer ikke i objektet."
**Fix:** Inline the employment: `"employments": [{"startDate": "YYYY-MM-DD"}]` on the employee POST.
**Note:** Employment is NOT auto-created if you omit the `employments` array.
