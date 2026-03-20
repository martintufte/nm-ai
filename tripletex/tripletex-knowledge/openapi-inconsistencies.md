# OpenAPI Spec Inconsistencies

Things the spec gets wrong, hides, or fails to document. You cannot avoid these by reading the spec alone.

## Employee `userType` is secretly required
**Spec says:** writable field, not marked required
**Reality:** POST fails 422 if omitted. Error: "Brukertype kan ikke være '0' eller tom."
**Fix:** Always include `"userType": "STANDARD"` (or `"EXTENDED"`, `"NO_ACCESS"`)
**Extra:** The error `field` is `null`, so you can't programmatically identify which field failed.

## Employee `department` is secretly required
**Spec says:** writable field, not marked required
**Reality:** POST fails 422 if omitted. Error: "department.id: Feltet må fylles ut."
**Fix:** Always include `"department": {"id": DEPT_ID}`

## Employee `email` required for STANDARD/EXTENDED users
**Spec says:** writable field, not marked required
**Reality:** Error: "Må angis for Tripletex-brukere." Only required when `userType` is STANDARD or EXTENDED, NOT for NO_ACCESS.

## Product vatType: not all VAT types are valid
**Spec says:** `vatType: VatType` with no constraints
**Reality:** Both id=1 (input 25%) AND id=3 (output 25%) are INVALID for products. Error: "Ugyldig mva-kode."
**Fix:** Omit vatType entirely. Product creates fine without it — VAT is applied at invoicing level, not product level.

## Project `startDate` is secretly required
**Spec says:** writable field, not marked required
**Reality:** POST fails 422 if omitted. Error: "Feltet må fylles ut."
**Fix:** Always include `"startDate": "YYYY-MM-DD"`

## Invoice requires orders (non-empty)
**Spec says:** `orders` is writable
**Reality:** `orders` cannot be null or empty. Error: "Listen kan ikke være tom." / "Kan ikke være null."
**Fix:** Always include at least one order with orderLines in the invoice POST.

## Invoice requires company bank account
**Reality:** POST fails if company has no bank account number registered. Error: "Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer."
**Fix:** PUT to `/ledger/account/{bankAccountId}` with `{"id":X,"version":V,"bankAccountNumber":"12345678903"}` before creating first invoice.

## Per diem `location` is secretly required
**Spec says:** writable field, not marked required
**Reality:** Error: "Kan ikke være null."
**Fix:** Always include `"location": "CityName"` in per diem POST.

## Rate categories have date ranges — most are expired
459 total rate categories exist. Only ~25 are valid for 2026 (from=2026-01-01, to=2026-12-31). They're at the END of the paginated list (offset ~400+). To find current ones you must either:
- Paginate through ALL results (expensive: ~10 API calls), or
- Filter by date in your query if the API supports it

## Error messages are in Norwegian
Key translations:
- "Feltet må fylles ut" = "Field must be filled in" (required)
- "Validering feilet" = "Validation failed"
- "Ugyldig mva-kode" = "Invalid VAT code"
- "Brukertype kan ikke være '0' eller tom" = "User type cannot be '0' or empty"
- "Feltet eksisterer ikke i objektet" = "Field does not exist in the object" (wrong field name)
- "Listen kan ikke være tom" = "List cannot be empty"
- "Kan ikke være null" = "Cannot be null"
- "Må angis for Tripletex-brukere" = "Must be specified for Tripletex users"

## Validation error `field` is often null or misleading
The `field` property in validationMessages can be `null` (e.g., userType error) or use internal names (e.g., "Internt felt (vatTypeId)") that don't match API field names.

## POST response for sub-resources may only contain URL
Mileage allowance and per diem POST responses return only `{"value":{"url":"..."}}` — no id/version in body. Parse the id from the URL if needed.

## PUT /employee requires `dateOfBirth`
**Spec says:** writable field, not marked required
**Reality:** PUT fails 422 if omitted. Error: "dateOfBirth: Feltet må fylles ut."
**Fix:** Always include `"dateOfBirth": "YYYY-MM-DD"` in employee PUT payloads. Not required for POST.

## Employees cannot be deleted via API
**Reality:** `DELETE /employee/{id}` returns 403 Forbidden, regardless of whether the employee has references.
**Fix:** Employees can only be deactivated, not deleted. There is no documented deactivation endpoint; this may require setting a flag via PUT.

## Invoices cannot be deleted
**Reality:** `DELETE /invoice/{id}` returns 403 Forbidden.
**Fix:** Use `PUT /invoice/{id}/:createCreditNote?date=...&comment=...` to void an invoice instead.

## Orders cannot be deleted if invoices exist
**Reality:** `DELETE /order/{id}` returns 422 if the order has generated invoices. Error: "Ordren kan ikke slettes. Fakturaer er generert."
**Fix:** In practice, orders with invoices are permanent.

## Product names must be unique
**Reality:** POST /product fails 422 if a product with the same name already exists. Error: "Produktnavnet X er allerede registrert."
**Fix:** Use unique product names per creation.

## Order `deliveryDate` is secretly required
**Spec says:** writable field, not marked required (Order has NO required fields in spec)
**Reality:** POST /invoice with inline orders fails 422 if `deliveryDate` is omitted. Error: "orders.deliveryDate: Kan ikke være null."
**Fix:** Always include `"deliveryDate"` in inline orders. Use the same date as `orderDate` if no specific delivery date is given.

## `priceIncludingVatCurrency` does NOT auto-calculate excl price
**Reality:** Setting `priceIncludingVatCurrency: 625.0` stores both incl and excl as the same value (625.0). There is no automatic VAT decomposition at the product level.
**Fix:** Always set `priceExcludingVatCurrency` explicitly. The incl/excl VAT split happens at invoicing time, not product creation.

## PUT silently ignores nested objects without their own `id`/`version`
**Spec says:** Nested objects like `postalAddress`, `physicalAddress` (type Address) are writable.
**Reality:** PUT returns 2xx but silently drops nested object updates if the nested object's own `id` and `version` are omitted. A subsequent GET shows the fields unchanged (or null).
**Observed:** `PUT /customer/{id}` with `postalAddress: {"addressLine1":"Storgata 45","postalCode":"0182","city":"Oslo"}` (no address id/version) → 2xx, but GET showed postalAddress fields as null.
**Fix:** Include the nested object's `id` and `version` from the previous GET or POST response:
```json
PUT /customer/{id}
{
  "id": CUST_ID, "version": CUST_V,
  "postalAddress": {"id": ADDR_ID, "version": ADDR_V, "addressLine1": "Storgata 45", "postalCode": "0182", "city": "Oslo"}
}
```
**Tip:** POST /customer returns `postalAddress.id` in the response even for name-only creation (address is auto-created). Cache this id to avoid an extra GET later. Newly created addresses start at `version: 0`.
**Note:** There is no standalone `/address` endpoint. Addresses are only managed through their parent entity.
