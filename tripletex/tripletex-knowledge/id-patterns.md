# ID Patterns and Response Shapes

## Reference format: `{id: X}` wrapper
All entity references in POST/PUT bodies use the wrapper object:
```json
{"customer": {"id": 12345}}
```
NOT raw integers. Applies to: `customer`, `employee`, `projectManager`, `department`, `product`, `vatType`, `productUnit`, `order`, `currency`, `costCategory`, `paymentType`, `rateType`, `travelExpense`, etc.

## Response shape: list endpoints (`GET /entity`)
```json
{
  "fullResultSize": 42,    // total matching records in DB
  "from": 0,               // pagination offset
  "count": 5,              // records returned in this page
  "versionDigest": "...",  // caching header
  "values": [...]          // array of entity objects
}
```
Pagination: use `?from=X&count=Y` query params.

## Response shape: single entity (`GET /entity/{id}`)
```json
{
  "value": { ... }         // single entity object with all fields
}
```

## Response shape: POST (create)
Most entities return the full created object:
```json
{
  "value": {
    "id": 12345,
    "version": 0,
    "url": "...",
    ...all fields...
  }
}
```
HTTP 201 on success.

**Exception:** Some sub-resources (mileage allowance, per diem compensation) return only:
```json
{
  "value": {
    "url": "kkpqfuj-amager.tripletex.dev/v2/travelExpense/mileageAllowance/6871397"
  }
}
```
Parse the id from the URL path if needed.

## Response shape: PUT (action endpoints like /:payment, /:createCreditNote)
Returns the entity object. HTTP 200. Credit note returns a NEW invoice object (the credit note itself).

## Response shape: DELETE
HTTP 204 No Content. Empty body.

## Response shape: errors
```json
{
  "status": 422,
  "code": 18000,
  "message": "Validering feilet.",
  "developerMessage": "VALIDATION_ERROR",
  "validationMessages": [
    {"field": "fieldName", "message": "Feltet må fylles ut.", "path": null, "rootId": null}
  ]
}
```
- `field` can be `null` or use internal names ("Internt felt (vatTypeId)")
- `code` 18000 = validation error, 16000 = request mapping failed (wrong field names)
- Messages in Norwegian (see gotchas.md for translations)

## Auto-assigned fields
- `id`: always auto-assigned on create
- `version`: starts at 0, increments on each update
- `url`: auto-generated `{host}/v2/{entityType}/{id}`
- `displayName`: auto-composed (e.g., employee: "{firstName} {lastName}")
- `employeeNumber`: auto-assigned if not provided
- `departmentNumber`: auto-assigned if not provided
- `customerNumber`: auto-assigned if not provided
- `invoiceNumber`: auto-assigned sequentially (1, 2, 3...)
- Travel expense `number`/`numberAsString`: auto-assigned (e.g., "1-2026")

## Version field and optimistic locking
Every entity has a `version` integer. When doing PUT updates:
1. GET the entity first to get current version
2. Include `"id": X, "version": V` in PUT body
3. If version mismatch, PUT fails (someone else modified it)

## Inline creation (general rule)
Any writable array-of-object field in the OpenAPI spec supports inline creation on POST. This means you can create parent + children in a single call by nesting the child objects in the array field. Nesting works multiple levels deep.

Verified inline fields:
- `Invoice.orders` → `[Order]` (and `Order.orderLines` → `[OrderLine]`)
- `Employee.employments` → `[Employment]` (and `Employment.employmentDetails` → `[EmploymentDetails]`)
- `TravelExpense.costs` → `[Cost]`
- `TravelExpense.perDiemCompensations` → `[PerDiemCompensation]`

To identify other inline-capable fields, look for non-readOnly properties with `type: array` and `items.$ref` in the OpenAPI spec.
