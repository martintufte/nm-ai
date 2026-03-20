# Department

## Dependencies
None — department can be created from scratch.

## Required Fields — POST /department

| Field | Required? | Notes |
|-------|-----------|-------|
| `name` | Yes | Sufficient alone for creation |

Optional fields: `departmentNumber` (auto-assigned if omitted), `departmentManager` (Employee ref), `isInactive`.

## Call-saving Patterns

- **POST returns full object** with `id`, `version`. Reuse directly when creating employees, projects, etc.
- Department is a dependency for Employee — create it first if needed, then pass the returned `id` immediately.

## Minimum Payload
```json
POST /department
{"name": "X"}
```

## Update — PUT /department/{id}
Requires `id` and `version`.
```json
PUT /department/{id}
{"id": X, "version": V, "name": "New Name"}
```

## Delete
`DELETE /department/{id}` → 204 (succeeds).

## API Reference

### GET /department
Query params: `id`, `name`, `departmentNumber`, `departmentManagerId`, `isInactive`

### POST /department
Add new department. Returns full object.

### GET /department/{id}
### PUT /department/{id}
### DELETE /department/{id}

### GET /department/query
Wildcard search. Query params: `id`, `query`, `isInactive`

### POST /department/list
Register new departments.
### PUT /department/list
Update multiple departments.
