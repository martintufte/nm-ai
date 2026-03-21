# Activity

## Dependencies
None — activities are standalone reference data.

## Required Fields — POST /activity

| Field | Required? | Notes |
|-------|-----------|-------|
| `name` | Yes | |
| `activityType` | **Yes (hidden)** | Error if omitted: "Kan ikke være null." Values: `GENERAL_ACTIVITY`, `PROJECT_GENERAL_ACTIVITY`, `PROJECT_SPECIFIC_ACTIVITY`, `TASK` |

Optional fields: `number` (string), `description` (string), `isChargeable` (boolean), `rate` (number), `costPercentage` (number).

## Call-saving Patterns

- **Search by name**: `GET /activity?name=X` — direct name match.
- **POST returns full object** with `id`, `version`. No GET needed.
- Activities are often pre-existing reference data — search before creating.

## Minimum Payload
```json
POST /activity
{"name": "Design", "activityType": "PROJECT_GENERAL_ACTIVITY"}
```

## Linking Activities to Projects

Activities must be linked to a project before they can be used in timesheet entries. Two approaches:

1. **Inline on project POST**: `"projectActivities": [{"activity": {"id": ACT_ID}}]`
2. **Separate call**: `POST /project/projectActivity {"activity": {"id": ACT_ID}, "project": {"id": PROJ_ID}}`

Prefer inline creation when creating the project.

## API Reference

### GET /activity
Query params: `id`, `name`, `number`, `description`, `isProjectActivity`, `isGeneral`, `isChargeable`, `isTask`, `isInactive`

### POST /activity
Create one activity. Returns full object.

### GET /activity/{id}

### POST /activity/list — create multiple activities

### GET /activity/>forTimeSheet
Find activities applicable for timesheet registration.
Query params: `projectId`, `employeeId`, `date`, `includeProjectActivity`
