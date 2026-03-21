# Unresolved Issues

Issues observed during testing that need further investigation.

## Task 8.1 — Timesheet + Project Invoice: 8 calls (optimal 6)

**Priority:** 2 (efficiency gap)

Agent made 2 extra calls: separate `GET /project/projectActivity` and `GET /project/hourlyRates` instead of getting them inline with the project.

**To investigate:**
- Does `GET /project?fields=projectActivities(*),hourlyRates(*)` return activity and rate data inline in a fresh sandbox?
- If so, the optimal 6-call sequence is: GET project (with expanded fields) + GET employee + POST timesheet + PUT hourlyRates + POST product + POST invoice

