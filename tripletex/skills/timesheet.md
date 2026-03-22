# Timesheet (Hours Registration)

## Dependencies
- **Employee** must exist
- **Project** must exist
- **Activity** must exist and be linked to the project (via projectActivity)

## Required Fields — POST /timesheet/entry

| Field | Required? | Notes |
|-------|-----------|-------|
| `employee` | Yes | `{"id": EMP_ID}` |
| `project` | Yes | `{"id": PROJ_ID}` |
| `activity` | Yes | `{"id": ACT_ID}` |
| `date` | Yes | ISO date |
| `hours` | Yes | number |

Only one entry per employee/date/activity/project combination is supported.

Optional fields: `comment` (string), `projectChargeableHours` (number).

## Call-saving Patterns

- **POST returns full object** with `id`, `version`. No GET needed.
- **Look up activity by name** in a single call: `GET /activity?name=X`
- **Look up project by name** in a single call: `GET /project?name=X` — the response includes `projectHourlyRates` with IDs, so you can PUT hourly rates without an extra GET.

## Minimum Payload
```json
POST /timesheet/entry
{"employee": {"id": EMP_ID}, "project": {"id": PROJ_ID}, "activity": {"id": ACT_ID}, "date": "YYYY-MM-DD", "hours": 8.0}
```

## API Reference

### GET /timesheet/entry
Query params: `id`, `employeeId`, `projectId`, `activityId`, `dateFrom` **(required)**, `dateTo` **(required)**, `comment`

### POST /timesheet/entry
Create one timesheet entry. Returns full object.

### GET /timesheet/entry/{id}
### PUT /timesheet/entry/{id}
### DELETE /timesheet/entry/{id}

### POST /timesheet/entry/list — create multiple entries
### PUT /timesheet/entry/list — update multiple entries

### GET /timesheet/entry/>recentActivities
Recent activities for the current user.

### GET /timesheet/entry/>recentProjects
Recent projects for the current user.

### GET /timesheet/entry/>totalHours
Query params: `employeeId`, `startDate`, `endDate`

---

## Timesheet Allocated (Budget Hours)

### GET /timesheet/allocated
Query params: `id`, `employeeId`, `projectId`, `activityId`, `dateFrom` **(required)**, `dateTo` **(required)**

### POST /timesheet/allocated
TimesheetAllocated writable fields: `employee`, `project`, `activity`, `date`, `hours`, `description`

### POST /timesheet/allocated/list
### PUT /timesheet/allocated/list
### GET /timesheet/allocated/{id}
### PUT /timesheet/allocated/{id}
### DELETE /timesheet/allocated/{id}

---

## Timesheet Month/Week (Approval)

### GET /timesheet/month/{id}
### GET /timesheet/month/byMonthNumber
Query params: `employeeIds`, `monthYear`

### PUT /timesheet/month/:approve
### PUT /timesheet/month/:complete
### PUT /timesheet/month/:reopen
### PUT /timesheet/month/:unapprove

### GET /timesheet/week
### PUT /timesheet/week/:approve
### PUT /timesheet/week/:complete
### PUT /timesheet/week/:reopen
### PUT /timesheet/week/:unapprove
