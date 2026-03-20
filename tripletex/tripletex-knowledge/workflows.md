# Workflows: Minimum-Step Recipes

## Create Employee
### NO_ACCESS (1 call, no email needed)
```
POST /employee
{"firstName":"X","lastName":"Y","userType":"NO_ACCESS","department":{"id":DEPT_ID}}
```

### STANDARD (1 call, needs email)
```
POST /employee
{"firstName":"X","lastName":"Y","userType":"STANDARD","email":"x@y.com","department":{"id":DEPT_ID}}
```

### With employment start date (1 call, inline)
```
POST /employee
{"firstName":"X","lastName":"Y","userType":"STANDARD","email":"x@y.com","department":{"id":DEPT_ID},"dateOfBirth":"YYYY-MM-DD","employments":[{"startDate":"YYYY-MM-DD"}]}
```
`startDate` is on Employment, not Employee — but employments can be inlined on the employee POST.
Employment is NOT auto-created if you omit the `employments` array.

## Create Customer (1 call)
```
POST /customer
{"name":"X"}
```

## Create Product (1 call)
```
POST /product
{"name":"X"}
```
Optional: `priceExcludingVatCurrency`, `productUnit: {"id": UNIT_ID}`. Do NOT set vatType.

## Create Department (1 call)
```
POST /department
{"name":"X"}
```

## Create Project (1 call, needs employee)
```
POST /project
{"name":"X","projectManager":{"id":EMP_ID},"isInternal":true,"startDate":"YYYY-MM-DD"}
```

## Full Invoice Workflow (1-2 setup calls + 1 invoice call + optional payment/credit)

### Prerequisites
- Customer exists (or create: 1 call)
- Product exists (or create: 1 call)
- Company has bank account number set (one-time setup, see below)

### One-time setup: Set bank account number
```
PUT /ledger/account/BANK_ACCOUNT_ID
{"id":BANK_ACCOUNT_ID,"version":V,"bankAccountNumber":"12345678903"}
```
Without this, invoice creation fails with "Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer."

### Create invoice with inline orders (1 call)
```
POST /invoice
{
  "invoiceDate": "YYYY-MM-DD",
  "invoiceDueDate": "YYYY-MM-DD",
  "customer": {"id": CUST_ID},
  "orders": [{
    "orderDate": "YYYY-MM-DD",
    "deliveryDate": "YYYY-MM-DD",
    "customer": {"id": CUST_ID},
    "orderLines": [{
      "product": {"id": PROD_ID},
      "count": 2
    }]
  }]
}
```

### Register payment (1 call, QUERY PARAMS not body)
```
PUT /invoice/{id}/:payment?paymentDate=YYYY-MM-DD&paymentTypeId=PAY_TYPE_ID&paidAmount=1000.0
```

### Create credit note (1 call, QUERY PARAMS not body)
```
PUT /invoice/{id}/:createCreditNote?date=YYYY-MM-DD&comment=reason
```
Returns a new invoice object (the credit note) with its own ID.

## Create Order + Order Lines (2 calls)
1. `POST /order` → `{"orderDate":"YYYY-MM-DD","deliveryDate":"YYYY-MM-DD","customer":{"id":X}}`
2. `POST /order/orderline` → `{"order":{"id":ORDER_ID},"product":{"id":PROD_ID},"count":3}`

## Travel Expense Workflow

### Create travel expense (1 call)
```
POST /travelExpense
{
  "employee": {"id": EMP_ID},
  "title": "Trip Name",
  "travelDetails": {
    "departureDate": "YYYY-MM-DD",
    "returnDate": "YYYY-MM-DD",
    "isDayTrip": false,
    "isForeignTravel": false,
    "departureFrom": "Oslo",
    "destination": "Bergen",
    "departureTime": "08:00",
    "returnTime": "18:00",
    "purpose": "Business meeting"
  }
}
```
NOTE: dates go inside `travelDetails`, NOT at top level.

### Add cost (1 call per cost)
```
POST /travelExpense/cost
{
  "travelExpense": {"id": TE_ID},
  "costCategory": {"id": CAT_ID},
  "paymentType": {"id": 32947574},
  "currency": {"id": 1},
  "amountCurrencyIncVat": 750.0,
  "date": "YYYY-MM-DD"
}
```
NOTE: field is `amountCurrencyIncVat`, NOT `amount`.

### Add mileage (1 call)
```
POST /travelExpense/mileageAllowance
{
  "travelExpense": {"id": TE_ID},
  "rateType": {"id": MILEAGE_RATE_CAT_ID},
  "date": "YYYY-MM-DD",
  "departureLocation": "Oslo",
  "destination": "Bergen",
  "km": 463,
  "rate": 3.5,
  "amount": 1620.5,
  "isCompanyCar": false
}
```

### Add per diem (1 call)
```
POST /travelExpense/perDiemCompensation
{
  "travelExpense": {"id": TE_ID},
  "rateType": {"id": PERDIEM_RATE_CAT_ID},
  "count": 2,
  "location": "Bergen",
  "overnightAccommodation": "HOTEL",
  "isDeductionForBreakfast": false
}
```
NOTE: `count` is number of days (integer). `location` is required.

### Add accommodation allowance (1 call)
```
POST /travelExpense/accommodationAllowance
{
  "travelExpense": {"id": TE_ID},
  "rateType": {"id": ACCOM_RATE_CAT_ID},
  "count": 1,
  "location": "Bergen",
  "address": "Testveien 1"
}
```
Use rate category 754 ("Ulegitimert - innland") or 761 ("Kompensasjonstillegg - skattepliktig").

### Passenger supplement for mileage
Passenger supplement is a SEPARATE mileage entry, not a boolean field.
```
POST /travelExpense/mileageAllowance
{
  "travelExpense": {"id": TE_ID},
  "rateType": {"id": 744},
  "date": "YYYY-MM-DD",
  "departureLocation": "Oslo",
  "destination": "Bergen",
  "km": 463,
  "rate": 1.0,
  "amount": 463.0,
  "isCompanyCar": false
}
```
Use rate category 744 ("Bil - passasjertillegg") — same km/route as main mileage.

## Delete Entities
Return 204 on success:
- `DELETE /department/{id}`
- `DELETE /customer/{id}` (fails if referenced by invoice)
- `DELETE /product/{id}` (fails if referenced by orderline)
- `DELETE /project/{id}`
- `DELETE /travelExpense/{id}` (succeeds even with sub-resources)

**Cannot delete:**
- `DELETE /employee/{id}` → 403 Forbidden (employees cannot be deleted via API)
- `DELETE /invoice/{id}` → 403 Forbidden (use credit note to void instead)
- `DELETE /order/{id}` → 422 if invoices exist (orders with invoices are permanent)

## Update Entities (PUT)
All require `id` and `version` in body (optimistic locking). GET first to obtain current version.
```
PUT /customer/{id}  {"id":X,"version":V,"name":"New Name"}
PUT /product/{id}   {"id":X,"version":V,"name":"X","priceExcludingVatCurrency":999.0}
PUT /employee/{id}  {"id":X,"version":V,"firstName":"X","lastName":"Y","userType":"NO_ACCESS","department":{"id":D},"dateOfBirth":"YYYY-MM-DD"}
```
**NOTE:** Employee PUT requires `dateOfBirth` (not required on POST). Error: "dateOfBirth: Feltet må fylles ut."

### Updating nested objects (e.g. postalAddress)
Nested objects with their own `id`/`version` (like Address) must include those fields or the update is silently ignored.
```
PUT /customer/{id}
{
  "id": CUST_ID, "version": CUST_V,
  "postalAddress": {"id": ADDR_ID, "version": ADDR_V, "addressLine1": "Storgata 45", "postalCode": "0182", "city": "Oslo"}
}
```
The address `id` is returned in the POST /customer response (even for name-only creation). Cache it to save a GET.

## Lookup Reference Data (GET, cache per session)
```
GET /employee?count=5                              → existing employees + their IDs
GET /department?count=5                             → existing departments
GET /ledger/vatType?count=50                        → VAT codes
GET /product/unit?count=50                          → units (stk, kg, etc.)
GET /currency?code=NOK                              → NOK currency id
GET /invoice/paymentType                            → payment types for invoicing
GET /travelExpense/costCategory?count=50            → cost categories
GET /travelExpense/rateCategory?from=400&count=60   → CURRENT rate categories (skip expired ones!)
GET /travelExpense/paymentType                      → travel payment types
GET /ledger/account?isBankAccount=true&count=20     → bank accounts
```

## Current Rate Categories (2026, sandbox)
### Per Diem (domestic)
| ID | Name |
|----|------|
| 738 | Dagsreise 6-12 timer - innland |
| 739 | Dagsreise over 12 timer - innland |
| 740 | Overnatting over 12 timer - innland |
| 741 | 6-12 timer over helt døgn - innland (etter overnatting) |
| 742 | Over 12 timer over helt døgn - innland (etter overnatting) |

### Per Diem (foreign)
| ID | Name |
|----|------|
| 755 | 6-12 timer over helt døgn - utlandet (etter overnatting) |
| 756 | Over 12 timer over helt døgn - utlandet (etter overnatting) |
| 757 | Dagsreise 6-12 timer - utland |
| 758 | Dagsreise over 12 timer - utland |
| 759 | Overnatting over 12 timer - utland |
| 760 | Overnatting over 28 døgn |

### Mileage
| ID | Name |
|----|------|
| 743 | Bil |
| 744 | Bil - passasjertillegg |
| 745 | Bil - tilhengertillegg |
| 746 | Bil - tillegg skogs- og anleggsveier |
| 747 | Bil - tillegg for frakt av utstyr og materiell |
| 748 | Tillegg ved fylling av drivstoff hvor bomavgift er inkludert |
| 749 | Motorsykkel opp til og med 125 ccm |
| 750 | Motorsykkel - over 125 ccm |
| 751 | Snøskuter og ATV (firehjuling) |
| 752 | Båt med motor |
| 753 | Andre motoriserte fremkomstmidler |

### Accommodation
| ID | Name |
|----|------|
| 754 | Ulegitimert - innland |
| 761 | Kompensasjonstillegg - skattepliktig |

**NOTE:** These IDs are sandbox-specific. In competition/production, look them up via `GET /travelExpense/rateCategory` with pagination past the expired entries, or use date filtering if available.
