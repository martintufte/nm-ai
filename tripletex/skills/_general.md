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
Pagination: `?from=X&count=Y`.

### Single entity (`GET /entity/{id}`)
```json
{"value": { ...entity... }}
```

### POST (create)
Returns the full created object with `id`, `version`, and all fields. HTTP 201.
```json
{"value": {"id": 12345, "version": 0, "url": "...", ...all fields...}}
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
Nested objects with their own `id`/`version` (like Address) must include those fields or the update is **silently ignored**. A subsequent GET will show the fields unchanged.

**Call-saving:** POST responses include nested object IDs even for minimal creation (e.g., `postalAddress.id` is returned on `POST /customer` even with name-only). Cache these to avoid extra GETs.

## Inline Creation
Any writable array-of-object field supports inline creation on POST. Create parent + children in a single call.

Verified inline fields:
- `Invoice.orders` → `[Order]` (and `Order.orderLines` → `[OrderLine]`) — 3 entities in 1 call
- `Employee.employments` → `[Employment]` (and `Employment.employmentDetails` → `[EmploymentDetails]`)
- `TravelExpense.costs` → `[Cost]`
- `TravelExpense.perDiemCompensations` → `[PerDiemCompensation]`

**Always prefer inline creation over separate calls when possible.**

## Auto-assigned Fields
Never set these — they're auto-generated:
- `id`, `version`, `url`
- `displayName` (composed from name fields)
- `employeeNumber`, `departmentNumber`, `customerNumber` (auto-assigned if omitted)
- `invoiceNumber` (sequential)

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
