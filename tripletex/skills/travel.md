# Travel Expense (+ Costs, Mileage, Per Diem, Accommodation)

## Dependencies
- **Employee** must exist

For sub-resources:
- **Cost**: CostCategory ID + TravelPaymentType ID + Currency ID
- **Mileage**: RateCategory ID (type=MILEAGE_ALLOWANCE, must have valid date range covering travel date)
- **Per Diem**: RateCategory ID (type=PER_DIEM, must have valid date range) + location string
- **Accommodation**: RateCategory ID (type=ACCOMMODATION_ALLOWANCE, valid date range) + location string
- **Passenger supplement**: RateCategory ID 744 (separate mileage entry, NOT a boolean flag)

## Required Fields — POST /travelExpense

| Field | Required? | Notes |
|-------|-----------|-------|
| `employee` | Yes | `{"id": EMP_ID}` |
| `travelDetails` | **Yes (hidden)** | Nested object — dates go INSIDE here, NOT at top level. Error if dates at top: "Feltet eksisterer ikke i objektet." |
| `travelDetails.departureDate` | Yes | ISO date, inside travelDetails |
| `travelDetails.returnDate` | Yes | ISO date, inside travelDetails |
| `travelDetails.isDayTrip` | Should set | boolean |
| `title` | No | Optional (verified: POST succeeds without it) |

Optional travelDetails fields: `isForeignTravel`, `departureFrom`, `destination`, `departureTime`, `returnTime`, `purpose`.

Other optional fields: `project`, `department`, `isChargeable`, `travelAdvance`.

## Inline Capabilities

All four sub-resource types can be inlined on `POST /travelExpense`:
- `"costs": [{...}]`
- `"mileageAllowances": [{...}]` (passenger supplement = separate entry with rateType 744)
- `"perDiemCompensations": [{...}]`
- `"accommodationAllowances": [{...}]`

All four can be combined in a single POST. See `_optimality_travel` for patterns.

## Minimum Payload
```json
POST /travelExpense
{
  "employee": {"id": EMP_ID},
  "travelDetails": {
    "departureDate": "YYYY-MM-DD",
    "returnDate": "YYYY-MM-DD",
    "isDayTrip": false
  }
}
```

With title and details:
```json
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

With ALL sub-resources inlined (saves 4+ calls):
```json
POST /travelExpense
{
  "employee": {"id": EMP_ID},
  "title": "Trip Name",
  "travelDetails": {
    "departureDate": "YYYY-MM-DD",
    "returnDate": "YYYY-MM-DD",
    "isDayTrip": false,
    "departureFrom": "Oslo",
    "destination": "Bergen"
  },
  "costs": [{
    "costCategory": {"id": CAT_ID},
    "paymentType": {"id": PAY_ID},
    "currency": {"id": 1},
    "amountCurrencyIncVat": 750.0,
    "date": "YYYY-MM-DD"
  }],
  "mileageAllowances": [{
    "rateType": {"id": 743},
    "date": "YYYY-MM-DD",
    "departureLocation": "Oslo",
    "destination": "Bergen",
    "km": 463,
    "rate": 3.5,
    "amount": 1620.5,
    "isCompanyCar": false
  }],
  "perDiemCompensations": [{
    "rateType": {"id": PERDIEM_RATE_CAT_ID},
    "count": 2,
    "location": "Bergen",
    "overnightAccommodation": "HOTEL",
    "isDeductionForBreakfast": false
  }],
  "accommodationAllowances": [{
    "rateType": {"id": 754},
    "count": 2,
    "location": "Bergen",
    "address": "Testveien 1"
  }]
}
```

---

## Travel Cost — POST /travelExpense/cost

| Field | Required? | Notes |
|-------|-----------|-------|
| `travelExpense` | Yes | `{"id": TE_ID}` |
| `costCategory` | Yes | `{"id": CAT_ID}`. Use only categories where `showOnTravelExpenses=true` |
| `paymentType` | Yes | `{"id": PAY_ID}` |
| `currency` | Yes | `{"id": 1}` for NOK |
| `amountCurrencyIncVat` | Yes | **NOT `amount`** — that field errors: "Feltet eksisterer ikke i objektet." |

Optional: `date`, `comments`, `rate`, `isChargeable`, `participants` (inline array).

```json
POST /travelExpense/cost
{
  "travelExpense": {"id": TE_ID},
  "costCategory": {"id": CAT_ID},
  "paymentType": {"id": PAY_ID},
  "currency": {"id": 1},
  "amountCurrencyIncVat": 750.0,
  "date": "YYYY-MM-DD"
}
```

---

## Travel Mileage — POST /travelExpense/mileageAllowance

| Field | Required? | Notes |
|-------|-----------|-------|
| `travelExpense` | Yes | `{"id": TE_ID}` |
| `rateType` | Yes | `{"id": RATE_CAT_ID}` — must be MILEAGE_ALLOWANCE category with valid date range |
| `date` | Yes | ISO date |
| `departureLocation` | Yes | string |
| `destination` | Yes | string |
| `km` | Yes | number |
| `rate` | Yes | number |
| `amount` | Yes | number (km × rate) |
| `isCompanyCar` | Yes | boolean |

**Note:** POST response may only return `{"value": {"url": ".../{id}"}}` — parse ID from URL if needed.

```json
POST /travelExpense/mileageAllowance
{
  "travelExpense": {"id": TE_ID},
  "rateType": {"id": 743},
  "date": "YYYY-MM-DD",
  "departureLocation": "Oslo",
  "destination": "Bergen",
  "km": 463,
  "rate": 3.5,
  "amount": 1620.5,
  "isCompanyCar": false
}
```

### Passenger Supplement
Passenger supplement is a **SEPARATE mileage entry**, NOT a boolean field. Adding `"passengerSupplement": true` errors: "Verdien er ikke av korrekt type for dette feltet."

Create a separate mileage allowance using rate category **744** ("Bil - passasjertillegg") with the same km/route:
```json
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

---

## Travel Per Diem — POST /travelExpense/perDiemCompensation

| Field | Required? | Notes |
|-------|-----------|-------|
| `travelExpense` | Yes | `{"id": TE_ID}` |
| `rateType` | Yes | `{"id": RATE_CAT_ID}` — PER_DIEM category |
| `count` | Yes | Number of days (integer). **NOT date ranges** — `countFrom`/`countTo` are GET query params only |
| `location` | **Yes (hidden)** | Not marked required in spec. Error: "Kan ikke være null." |
| `overnightAccommodation` | Yes | string enum: `"HOTEL"`, `"NONE"`, etc. |

Optional: `countryCode`, `travelExpenseZoneId`, `address`, `rate`, `amount`, `isDeductionForBreakfast`, `isDeductionForLunch`, `isDeductionForDinner`.

**Note:** POST response may only return `{"value": {"url": ".../{id}"}}`.

```json
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

---

## Accommodation Allowance — POST /travelExpense/accommodationAllowance

| Field | Required? | Notes |
|-------|-----------|-------|
| `travelExpense` | Yes | `{"id": TE_ID}` |
| `rateType` | Yes | `{"id": ACCOM_RATE_CAT_ID}` — ACCOMMODATION_ALLOWANCE category |
| `count` | Yes | Number of nights (integer) |
| `location` | Yes | string |

Optional: `address`, `rate`, `amount`, `zone`.

```json
POST /travelExpense/accommodationAllowance
{
  "travelExpense": {"id": TE_ID},
  "rateType": {"id": 754},
  "count": 1,
  "location": "Bergen",
  "address": "Testveien 1"
}
```
Use rate category 754 ("Ulegitimert - innland") or 761 ("Kompensasjonstillegg - skattepliktig").

---

## Delete
`DELETE /travelExpense/{id}` → 204 (succeeds even with sub-resources attached).

## Current Rate Categories (2026, sandbox)

### Per Diem — Domestic
| ID | Name |
|----|------|
| 738 | Dagsreise 6-12 timer - innland |
| 739 | Dagsreise over 12 timer - innland |
| 740 | Overnatting over 12 timer - innland |
| 741 | 6-12 timer over helt døgn - innland (etter overnatting) |
| 742 | Over 12 timer over helt døgn - innland (etter overnatting) |

### Per Diem — Foreign
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

**NOTE:** These IDs are sandbox-specific. In competition/production, look them up via `GET /travelExpense/rateCategory?from=400&count=60`.

---

## API Reference

### GET /travelExpense
Query params: `employeeId`, `departmentId`, `projectId`, `projectManagerId`, `departureDateFrom`, `returnDateTo`, `state`

### POST /travelExpense
Create travel expense. Returns full object.

### GET /travelExpense/{id}
### PUT /travelExpense/{id}
### DELETE /travelExpense/{id}

### PUT /travelExpense/:approve
### PUT /travelExpense/:deliver
### PUT /travelExpense/:unapprove
### PUT /travelExpense/:undeliver
### PUT /travelExpense/:copy — query params: `id` **(required)**
### PUT /travelExpense/:createVouchers — query params: `date` **(required)**
### PUT /travelExpense/{id}/convert

### POST /travelExpense/cost
### GET /travelExpense/cost
Query params: `travelExpenseId`, `vatTypeId`, `currencyId`, `rateFrom`, `rateTo`, `amountFrom`, `amountTo`, `location` (+more)
### PUT /travelExpense/cost/list — update multiple costs
### GET /travelExpense/cost/{id}
### PUT /travelExpense/cost/{id}
### DELETE /travelExpense/cost/{id}

### GET /travelExpense/costCategory
Query params: `id`, `description`, `isInactive`, `showOnEmployeeExpenses`, `query`
### GET /travelExpense/costCategory/{id}

### POST /travelExpense/mileageAllowance
### GET /travelExpense/mileageAllowance
Query params: `travelExpenseId`, `rateTypeId`, `kmFrom`, `kmTo`, `departureLocation`, `destination` (+more)
### GET /travelExpense/mileageAllowance/{id}
### PUT /travelExpense/mileageAllowance/{id}
### DELETE /travelExpense/mileageAllowance/{id}

### POST /travelExpense/perDiemCompensation
### GET /travelExpense/perDiemCompensation
Query params: `travelExpenseId`, `rateTypeId`, `overnightAccommodation`, `countFrom`, `countTo`, `location` (+more)
### GET /travelExpense/perDiemCompensation/{id}
### PUT /travelExpense/perDiemCompensation/{id}
### DELETE /travelExpense/perDiemCompensation/{id}

### POST /travelExpense/accommodationAllowance
### GET /travelExpense/accommodationAllowance
Query params: `travelExpenseId`, `rateTypeId`, `countFrom`, `countTo`, `location` (+more)
### GET /travelExpense/accommodationAllowance/{id}
### PUT /travelExpense/accommodationAllowance/{id}
### DELETE /travelExpense/accommodationAllowance/{id}

### Cost participants
### POST /travelExpense/costParticipant
CostParticipant writable fields: `displayName`, `employeeId` (int32 — optional, if participant is an employee), `cost` (Cost ref).
### POST /travelExpense/costParticipant/createCostParticipantAdvanced
Query params: `costId` **(required)**, `employeeId` **(required)**
### POST /travelExpense/costParticipant/list
### DELETE /travelExpense/costParticipant/list
### GET /travelExpense/costParticipant/{id}
### DELETE /travelExpense/costParticipant/{id}

### Passengers
### POST /travelExpense/passenger
Passenger writable fields: `name`, `mileageAllowance` (MileageAllowance ref)
### POST /travelExpense/passenger/list
### DELETE /travelExpense/passenger/list
### GET /travelExpense/passenger
Query params: `mileageAllowance`, `name`
### GET /travelExpense/passenger/{id}
### PUT /travelExpense/passenger/{id}
### DELETE /travelExpense/passenger/{id}

### Driving stops
### POST /travelExpense/drivingStop
DrivingStop writable fields: `locationName`, `latitude` (number), `longitude` (number), `sortIndex` (int32), `type` (int32), `mileageAllowance` (MileageAllowance ref)
### GET /travelExpense/drivingStop/{id}
### DELETE /travelExpense/drivingStop/{id}

### GET /travelExpense/paymentType
Query params: `id`, `description`, `isInactive`, `showOnEmployeeExpenses`, `query`
### GET /travelExpense/paymentType/{id}

### GET /travelExpense/rateCategory
Query params: `type`, `name`, `travelReportRateCategoryGroupId`, `isValidDayTrip`, `isValidAccommodation`, `isValidDomestic`, `requiresZone` (+more)
### GET /travelExpense/rateCategory/{id}

### GET /travelExpense/rateCategoryGroup
Query params: `name`, `isForeignTravel`, `dateFrom`, `dateTo`
### GET /travelExpense/rateCategoryGroup/{id}

### GET /travelExpense/rate
Query params: `rateCategoryId`, `type`, `isValidDayTrip`, `isValidAccommodation`, `isValidDomestic`, `isValidForeignTravel`, `dateFrom`, `dateTo` (+more)
### GET /travelExpense/rate/{id}

### GET /travelExpense/zone
Query params: `id`, `code`, `isDisabled`, `query`, `date`
### GET /travelExpense/zone/{id}

### GET /travelExpense/settings

### POST /travelExpense/{travelExpenseId}/attachment
### POST /travelExpense/{travelExpenseId}/attachment/list
### GET /travelExpense/{travelExpenseId}/attachment
### DELETE /travelExpense/{travelExpenseId}/attachment
