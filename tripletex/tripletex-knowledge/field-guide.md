# Field Guide: Actually-Required vs Spec-Required

The OpenAPI spec does NOT distinguish required from optional on POST. This file captures empirically verified requirements.

## Employee (`POST /employee`)
Minimum for `NO_ACCESS`:
```json
{"firstName":"X","lastName":"Y","userType":"NO_ACCESS","department":{"id":DEPT_ID}}
```
Minimum for `STANDARD`:
```json
{"firstName":"X","lastName":"Y","userType":"STANDARD","email":"x@y.com","department":{"id":DEPT_ID}}
```
- `firstName`: required
- `lastName`: required
- `userType`: **REQUIRED (not in spec).** Values: `"STANDARD"`, `"EXTENDED"`, `"NO_ACCESS"`. Error if omitted: "Brukertype kan ikke være '0' eller tom."
- `department`: **REQUIRED (not in spec).** Must be `{"id": X}`. Error: "department.id: Feltet må fylles ut."
- `email`: **REQUIRED for STANDARD/EXTENDED users.** Error: "Må angis for Tripletex-brukere." Not required for NO_ACCESS.
- `phoneNumberMobile`: optional, accepted on POST
- `address`: optional, accepted as `{"addressLine1":"...","postalCode":"...","city":"..."}` on POST
- `dateOfBirth`: optional on POST, **REQUIRED on PUT** (see gotcha #18)
- `startDate`: **NOT a field on Employee** — belongs to Employment sub-resource (see gotcha #24)

## Employment (`POST /employee/employment`)
Minimum:
```json
{"employee": {"id": EMP_ID}, "startDate": "YYYY-MM-DD"}
```
- `employee`: required `{"id": X}`
- `startDate`: required (ISO date string)
- Employment is NOT auto-created when creating an employee — must be explicitly created

## Customer (`POST /customer`)
Minimum: `{"name": "X"}` → 201
- `name`: required (and sufficient alone)
- `isPrivateIndividual`: optional boolean, accepted on POST
- `postalAddress`: optional, accepted as `{"addressLine1":"...","postalCode":"...","city":"..."}`

## Product (`POST /product`)
Minimum: `{"name": "X"}` → 201
- `name`: required (and sufficient alone)
- `priceExcludingVatCurrency`: optional, defaults to 0
- `vatType`: optional. **INVALID for output VAT codes** (id=3, 31, 32). See gotchas.
- `productUnit`: optional
- `priceIncludingVatCurrency`: optional, accepted but does NOT auto-calculate excl price (both values stored as-is)
- `name`: must be unique across all products (see gotcha #22)

## Department (`POST /department`)
Minimum: `{"name": "X"}` → 201
- `name`: required (and sufficient alone)
- `departmentNumber`: optional, auto-assigned if omitted

## Project (`POST /project`)
Minimum:
```json
{"name":"X","projectManager":{"id":EMP_ID},"isInternal":true,"startDate":"YYYY-MM-DD"}
```
- `name`: required
- `projectManager`: required `{"id": X}`
- `isInternal`: required (boolean)
- `startDate`: **REQUIRED (not in spec).** Error: "Feltet må fylles ut."

## Order (`POST /order`)
Minimum:
```json
{"orderDate":"YYYY-MM-DD","deliveryDate":"YYYY-MM-DD","customer":{"id":X}}
```

## Invoice (`POST /invoice`)
Minimum:
```json
{
  "invoiceDate":"YYYY-MM-DD",
  "invoiceDueDate":"YYYY-MM-DD",
  "customer":{"id":X},
  "orders":[{...at least one with orderLines...}]
}
```
- `orders`: **REQUIRED and non-empty.** Error: "Listen kan ikke være tom." / "Kan ikke være null."
- **PREREQUISITE:** Company must have a bank account number set on a bank ledger account. Error: "Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer."

## Invoice Payment (`PUT /invoice/{id}/:payment`)
**Uses QUERY PARAMS, not request body!**
```
PUT /invoice/{id}/:payment?paymentDate=YYYY-MM-DD&paymentTypeId=X&paidAmount=1000.0
```
All three query params required. Send empty body or no body.

## Credit Note (`PUT /invoice/{id}/:createCreditNote`)
**Uses QUERY PARAMS, not request body!**
```
PUT /invoice/{id}/:createCreditNote?date=YYYY-MM-DD&comment=reason
```
`date` required. `comment` optional. Returns a new invoice object (the credit note).

## Travel Expense (`POST /travelExpense`)
Minimum:
```json
{
  "employee":{"id":X},
  "title":"Trip Name",
  "travelDetails":{
    "departureDate":"YYYY-MM-DD",
    "returnDate":"YYYY-MM-DD",
    "isDayTrip":true
  }
}
```
- `employee`: required
- `title`: **optional** (verified: POST succeeds without it)
- `travelDetails`: **REQUIRED nested object** containing dates. Putting `departureDate`/`returnDate` at top level fails: "Feltet eksisterer ikke i objektet."
- `travelDetails.departureDate`: required
- `travelDetails.returnDate`: required
- `travelDetails.isDayTrip`: should be set (boolean)

## Travel Cost (`POST /travelExpense/cost`)
Minimum:
```json
{
  "travelExpense":{"id":X},
  "costCategory":{"id":CAT_ID},
  "paymentType":{"id":PAY_ID},
  "currency":{"id":1},
  "amountCurrencyIncVat":750.0,
  "date":"YYYY-MM-DD"
}
```
- `amountCurrencyIncVat`: the correct field name. **NOT `amount`** — that field "doesn't exist in the object" for POST.
- `date`: optional (works without it too)
- `costCategory`: required. Use only categories where `showOnTravelExpenses=true` for travel.

## Travel Mileage (`POST /travelExpense/mileageAllowance`)
Minimum:
```json
{
  "travelExpense":{"id":X},
  "rateType":{"id":RATE_CAT_ID},
  "date":"YYYY-MM-DD",
  "departureLocation":"Oslo",
  "destination":"Bergen",
  "km":463,
  "rate":3.5,
  "amount":1620.5,
  "isCompanyCar":false
}
```
- `rateType`: must be a MILEAGE_ALLOWANCE category with valid date range covering travel date

## Travel Per Diem (`POST /travelExpense/perDiemCompensation`)
Minimum:
```json
{
  "travelExpense":{"id":X},
  "rateType":{"id":RATE_CAT_ID},
  "count":2,
  "location":"Bergen",
  "overnightAccommodation":"HOTEL",
  "isDeductionForBreakfast":false
}
```
- `location`: **REQUIRED (not in spec).** Error: "Kan ikke være null."
- `count`: number of days (integer), NOT a date range
- `overnightAccommodation`: string enum, e.g. `"HOTEL"`, `"NONE"`
- **NOT `countFrom`/`countTo`** — those are GET query params only

## Accommodation Allowance (`POST /travelExpense/accommodationAllowance`)
Minimum:
```json
{
  "travelExpense": {"id": TE_ID},
  "rateType": {"id": ACCOM_RATE_CAT_ID},
  "count": 1,
  "location": "Bergen",
  "address": "Testveien 1"
}
```
- `travelExpense`: required
- `rateType`: required, must be ACCOMMODATION_ALLOWANCE category (e.g., id=754 "Ulegitimert - innland")
- `count`: number of nights (integer)
- `location`: required
- `address`: optional

## Deletions (fully verified)
- `DELETE /department/{id}` → 204 (succeeds)
- `DELETE /customer/{id}` → 204 (succeeds, if no invoice references)
- `DELETE /product/{id}` → 204 (succeeds, if no orderline references)
- `DELETE /project/{id}` → 204 (succeeds)
- `DELETE /travelExpense/{id}` → 204 (succeeds, even with sub-resources)
- `DELETE /employee/{id}` → **403 Forbidden** (employees cannot be deleted via API)
- `DELETE /invoice/{id}` → **403 Forbidden** (use credit note to void)
- `DELETE /order/{id}` → **422** if invoices exist ("Ordren kan ikke slettes. Fakturaer er generert.")
