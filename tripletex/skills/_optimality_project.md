# Optimality — Project

## Inline participants + activities: 1 POST (not 3)

Both participants and project activities can be inlined on `POST /project`.

Bad (3 calls):
```
POST /project {...}                                           → id=P
POST /project/participant {"project":{"id":P},"employee":{"id":E}}
POST /project/projectActivity {"project":{"id":P},"activity":{"id":A}}
```

Good (1 call):
```
POST /project {
  "name": "...", "projectManager": {"id": PM},
  "isInternal": true, "startDate": "...",
  "participants": [{"employee": {"id": E}}],
  "projectActivities": [{"activity": {"id": A}}]
}
```

Both arrays accept multiple entries.

## Project manager: use admin (don't create)

Only the admin employee has `AUTH_PROJECT_MANAGER` entitlement. Use `GET /token/session/>whoAmI` to get the admin employee ID. Don't try to grant entitlements — `grantEntitlementsByTemplate` returns 404 on sandbox.

## Timesheet needs activity linked to project

Timesheet entries require the activity to be linked to the project via `projectActivities`. Inline the activity on project creation to avoid a separate `POST /project/projectActivity` call.

## GET /project returns linked entities inline

`GET /project` returns `customer.id`, `projectManager.id`, `department.id`, `projectActivities`, and `projectHourlyRates` inline. Don't make separate GETs for these — extract IDs directly from the project response.

Bad (2 calls):
```
GET /project?name=X          → customer.id = C
GET /customer?customerName=X → same id C you already had
```

Good (1 call):
```
GET /project?name=X          → customer.id = C, use directly
```
