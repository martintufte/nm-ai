# Optimality — Travel Expense

## Inline all sub-resources: 1 POST (not 5)

ALL four sub-resource types can be inlined in a single `POST /travelExpense`.

Bad (5 calls):
```
POST /travelExpense {...}                           → id=T
POST /travelExpense/cost {..., travelExpense:{id:T}}
POST /travelExpense/mileageAllowance {...}
POST /travelExpense/perDiemCompensation {...}
POST /travelExpense/accommodationAllowance {...}
```

Good (1 call):
```
POST /travelExpense {
  ...,
  "costs": [{...}],
  "mileageAllowances": [{...}],
  "perDiemCompensations": [{...}],
  "accommodationAllowances": [{...}]
}
```

All four arrays are optional — include only what the task requires.

## Passenger supplement: same array (not a separate POST)

Passenger supplement is a SECOND entry in `mileageAllowances` with rateType 744 — not a boolean flag, not a separate POST.

Bad (3 calls):
```
POST /travelExpense {...}
POST /travelExpense/mileageAllowance {rateType:{id:743}, km:520, ...}
POST /travelExpense/mileageAllowance {rateType:{id:744}, km:520, ...}
```

Good (1 call):
```
POST /travelExpense {
  ...,
  "mileageAllowances": [
    {"rateType": {"id": 743}, "km": 520, ...},
    {"rateType": {"id": 744}, "km": 520, ...}
  ]
}
```

## Cost category + payment type: 2 lookups (unavoidable)

`costCategory` and `paymentType` IDs are reference data. You must look them up:
```
GET /travelExpense/costCategory?count=50
GET /travelExpense/paymentType
```
These 2 calls are unavoidable when the task includes costs. They can run before the single inline POST.

## Rate categories: skip expired ones

Current 2026 rate categories start at offset ~400. Don't paginate from 0.
```
GET /travelExpense/rateCategory?from=400&count=60
```
