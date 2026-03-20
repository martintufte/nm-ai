# General Tripletex API Patterns

## Reference Format
All entity references in POST/PUT bodies use wrapper objects:
```json
{"customer": {"id": 12345}}
```
NOT raw integers. Applies to all foreign key fields: `customer`, `employee`, `department`, `product`, `projectManager`, `vatType`, `productUnit`, `order`, `currency`, `costCategory`, `paymentType`, `rateType`, `travelExpense`, etc.

## Response Shapes

### List endpoints (`GET /entity`)
```json
{
  "fullResultSize": 42,
  "from": 0,
  "count": 5,
  "versionDigest": "...",
  "values": [...]
}
```
Pagination: `?from=X&count=Y`. The `fields` query parameter filters response fields, but avoid it unless you are certain of the exact DTO field names — wrong names cause HTTP 400, wasting a call.

**List GETs return full objects** — each item in `values[]` has `id`, `version`, and all nested objects (e.g., `postalAddress` with its own `id`). No need to re-GET by ID after finding an entity in a list response.

### Single entity (`GET /entity/{id}`)
```json
{"value": { ...entity... }}
```

### POST (create)
Returns the full created object with `id`, `version`, and all fields. HTTP 201.
```json
{"value": {"id": 12345, "version": 1, "url": "...", ...all fields...}}
```
**Call-saving:** Always reuse `id` and `version` from POST responses — no need to GET after creating.

**Exception:** Some travel sub-resources (mileage allowance, per diem) return only `{"value": {"url": ".../{id}"}}`. Parse the id from the URL if needed.

### DELETE
HTTP 204 No Content. Empty body.

### Errors
```json
{
  "status": 422,
  "code": 18000,
  "message": "Validering feilet.",
  "validationMessages": [{"field": "fieldName", "message": "Feltet må fylles ut."}]
}
```
- `field` can be `null` or use internal names that don't match API field names
- Code 18000 = validation error, 16000 = wrong field names
- Messages are in Norwegian. Key translations:
  - "Feltet må fylles ut" = "Field must be filled in" (required)
  - "Validering feilet" = "Validation failed"
  - "Ugyldig mva-kode" = "Invalid VAT code"
  - "Brukertype kan ikke være '0' eller tom" = "User type cannot be '0' or empty"
  - "Feltet eksisterer ikke i objektet" = "Field does not exist in the object"
  - "Listen kan ikke være tom" = "List cannot be empty"
  - "Kan ikke være null" = "Cannot be null"
  - "Må angis for Tripletex-brukere" = "Must be specified for Tripletex users"

## Version Field and Optimistic Locking
Every entity has a `version` integer. For PUT updates:
1. Include `"id": X, "version": V` in body
2. If version mismatch → PUT fails

**Call-saving:** If you just created the entity, reuse `id` and `version` from the POST response — skip the GET.

## Nested Object Updates (PUT)
<!-- Corrected: address without id/version is NOT silently ignored — it creates a new address object replacing the old one. Verified 2026-03-20. -->
For nested Address objects on customer/employee PUTs: including address data **without** `id`/`version` creates a **new address object** (old one is replaced). This is the simplest pattern — no need to track address IDs.

Do NOT try to reference an old address `id` on a different PUT — Tripletex rejects reusing address IDs across operations.

## Inline Creation
Any writable array-of-object field supports inline creation on POST. Create parent + children in a single call.

Verified inline fields:
- `Invoice.orders` → `[Order]` (and `Order.orderLines` → `[OrderLine]`) — 3 entities in 1 call
- `Employee.employments` → `[Employment]` (and `Employment.employmentDetails` → `[EmploymentDetails]`)
- `TravelExpense.costs` → `[Cost]`
- `TravelExpense.perDiemCompensations` → `[PerDiemCompensation]`
- `Project.participants` → `[ProjectParticipant]`

**Always prefer inline creation over separate calls when possible.**

### PUT action endpoints (`:payment`, `:createCreditNote`)
Returns the entity object. HTTP 200. Credit note returns a **new invoice object** (the credit note itself) with its own ID.

## Auto-assigned Fields
Never set these — they're auto-generated:
- `id`, `version` (starts at 1), `url`
- `displayName` (composed from name fields)
- `customerNumber` (auto-assigned if omitted)
- `invoiceNumber` (sequential)
- Travel expense `number`/`numberAsString` (e.g., "1-2026")

**Not auto-assigned** (default to empty string): `employeeNumber`, `departmentNumber`. Set explicitly if needed.

**Tip:** To identify inline-capable fields beyond the verified list, look for non-readOnly properties with `type: array` and `items.$ref` in the OpenAPI spec.

## Lookup Reference Data (cache per session)
```
GET /employee?count=5                              → existing employees
GET /department?count=5                             → existing departments
GET /ledger/vatType?count=50                        → VAT codes
GET /product/unit?count=50                          → units (stk, kg, etc.)
GET /currency?code=NOK                              → NOK currency id
GET /invoice/paymentType                            → invoice payment types
GET /travelExpense/costCategory?count=50            → cost categories
GET /travelExpense/rateCategory?from=400&count=60   → CURRENT 2026 rate categories
GET /travelExpense/paymentType                      → travel payment types
GET /ledger/account?isBankAccount=true&count=20     → bank accounts
```
