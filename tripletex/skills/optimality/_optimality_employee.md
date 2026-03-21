# Optimality — Employee

## Inline employment + details: 1 POST (not 3)

Employee, employment, and employment details can all be created in a single `POST /employee`.

Bad (3 calls):
```
POST /employee {...}                                              → id=E
POST /employee/employment {"employee":{"id":E},"startDate":"..."}  → id=M
POST /employee/employment/details {"employment":{"id":M},"date":"...","employmentType":"ORDINARY","employmentForm":"PERMANENT"}
```

Good (1 call):
```
POST /employee {
  "firstName":"X", "lastName":"Y", "userType":"STANDARD",
  "email":"x@y.com", "department":{"id":D},
  "dateOfBirth":"YYYY-MM-DD",
  "employments": [{
    "startDate": "YYYY-MM-DD",
    "employmentDetails": [{
      "date": "YYYY-MM-DD",
      "employmentType": "ORDINARY",
      "employmentForm": "PERMANENT"
    }]
  }]
}
```

**Note:** `dateOfBirth` becomes required when inlining employments. Employment is NOT auto-created if you omit the `employments` array.

## Department lookup: 1 call (unavoidable)

Department is a hidden required field. If the task names a department, look it up:
```
GET /department?name=X
```
If the task doesn't name one, use `GET /department?count=1` to grab any existing department.

## Sub-resources (standardTime, hourlyCostAndRate, nextOfKin): separate POSTs

These cannot be inlined on employee creation — each requires its own POST after the employee exists. But reuse the employee ID from the POST response; don't GET it again.
