# Employee

## Dependencies
- **Department** must exist first (or create one: `POST /department {"name":"X"}`)

## Required Fields — POST /employee

| Field | Required? | Notes |
|-------|-----------|-------|
| `firstName` | Yes | |
| `lastName` | Yes | |
| `userType` | **Yes (hidden)** | Not marked required in spec. Error if omitted: "Brukertype kan ikke være '0' eller tom." Values: `"NO_ACCESS"` = no system login, cannot access Tripletex; `"STANDARD"` = limited system access, can log in (requires `email`); `"EXTENDED"` = full system access, can log in (requires `email`). |
| `department` | **Yes (hidden)** | Not marked required in spec. Must be `{"id": DEPT_ID}`. Error: "department.id: Feltet må fylles ut." |
| `email` | Conditional | Required for STANDARD/EXTENDED. Not required for NO_ACCESS. Error: "Må angis for Tripletex-brukere." |
| `dateOfBirth` | No on POST | **Required when inlining `employments`** on POST. NOT required on PUT despite earlier documentation. |
| `startDate` | **Not a field** | Belongs to Employment, not Employee. Including it errors: "Feltet eksisterer ikke i objektet." Inline via `employments` array instead. |

Other accepted optional fields: `employeeNumber`, `phoneNumberMobile`, `phoneNumberMobileCountry` (Country ref), `phoneNumberHome`, `phoneNumberWork`, `address` (as `{"addressLine1":"...","postalCode":"...","city":"..."}`), `nationalIdentityNumber`, `dnumber` (Norwegian D-number), `internationalId` (InternationalId ref), `bankAccountNumber`, `iban`, `bic` (SWIFT code), `creditorBankCountryId` (int32), `usesAbroadPayment` (boolean — domestic vs abroad remittance), `comments`, `isContact` (boolean — external contact, not employee), `employeeCategory` (EmployeeCategory ref), `holidayAllowanceEarned` (HolidayAllowanceEarned ref).

## Call-saving Patterns

- **POST returns the full created object** with `id`, `version`, and all fields — no need to GET after creating.
- **Inline employments on POST**: include `"employments":[{"startDate":"YYYY-MM-DD"}]` in the employee POST body to create employee + employment in 1 call instead of 2. Employment is NOT auto-created if you omit the array. **Note:** `dateOfBirth` becomes required when inlining employments.
- **Inline employment details**: `employmentDetails` can be nested inside each employment object in the `employments` array, creating employee + employment + details in a single call.
- **Cache department ID**: if you just created a department, reuse its returned ID directly — don't GET /department to look it up.
- **PUT needs a GET first** (for `version`), but if you just created the employee, reuse `id` and `version` from the POST response.

## Minimum Payloads

### NO_ACCESS (1 call, no email needed)
```json
POST /employee
{"firstName":"X","lastName":"Y","userType":"NO_ACCESS","department":{"id":DEPT_ID}}
```

### STANDARD (1 call, needs email)
```json
POST /employee
{"firstName":"X","lastName":"Y","userType":"STANDARD","email":"x@y.com","department":{"id":DEPT_ID}}
```

### With employment start date (1 call, inline)
```json
POST /employee
{
  "firstName":"X","lastName":"Y","userType":"STANDARD",
  "email":"x@y.com","department":{"id":DEPT_ID},
  "dateOfBirth":"YYYY-MM-DD",
  "employments":[{"startDate":"YYYY-MM-DD"}]
}
```

### Full inline (employee + employment + details, 1 call)
```json
POST /employee
{
  "firstName":"X","lastName":"Y","userType":"STANDARD",
  "email":"x@y.com","department":{"id":DEPT_ID},
  "dateOfBirth":"YYYY-MM-DD",
  "employments":[{
    "startDate":"YYYY-MM-DD",
    "employmentDetails":[{
      "date":"YYYY-MM-DD",
      "employmentType":"ORDINARY",
      "employmentForm":"PERMANENT"
    }]
  }]
}
```

## Update — PUT /employee/{id}

Requires `id` and `version` in the body.
```json
PUT /employee/{id}
{
  "id":X, "version":V,
  "firstName":"X", "lastName":"Y",
  "userType":"NO_ACCESS",
  "department":{"id":DEPT_ID}
}
```
<!-- Corrected: dateOfBirth is NOT required on PUT. Verified against sandbox 2026-03-20. -->

If you just created the employee, reuse `id` and `version` from the POST response — skip the GET.

## Delete
`DELETE /employee/{id}` → **403 Forbidden**. Employees cannot be deleted via API.

## Auto-assigned Fields
- `id`, `version`, `url`, `displayName` (composed as "firstName lastName")
- `employeeNumber` (auto-assigned if not provided)

## Employment Sub-resource

Employment is a separate entity linked to an employee. Prefer inlining on employee POST (see above) over creating separately.

### POST /employee/employment
```json
{"employee":{"id":EMP_ID},"startDate":"YYYY-MM-DD"}
```
- `employee`: required `{"id": X}`
- `startDate`: required (ISO date)
- Returns full created object with `id` and `version` — no GET needed after.

### Employment writable fields
`employmentId`, `startDate`, `endDate`, `employmentEndReason`, `division`, `lastSalaryChangeDate`, `noEmploymentRelationship`, `isMainEmployer`, `taxDeductionCode`, `employmentDetails` (inline array), `latestSalary`, `isRemoveAccessAtEmploymentEnded`.

### Employment Details — POST /employee/employment/details
```json
{"employment":{"id":EMPLOYMENT_ID},"date":"YYYY-MM-DD","employmentType":"ORDINARY","employmentForm":"PERMANENT"}
```
Writable fields: `employment`, `date`, `employmentType`, `employmentForm`, `maritimeEmployment`, `remunerationType`, `workingHoursScheme`, `shiftDurationHours`, `occupationCode`, `percentageOfFullTimeEquivalent`, `annualSalary`, `hourlyWage`, `payrollTaxMunicipalityId`.

Prefer inlining via `employments[].employmentDetails[]` on employee POST instead of separate calls.

## Next of Kin — POST /employee/nextOfKin

```json
{"employee": {"id": EMP_ID}, "name": "Contact Name", "phoneNumber": "12345678", "typeOfRelationship": "SPOUSE"}
```
Writable fields: `employee` (ref), `name`, `phoneNumber`, `address`, `typeOfRelationship` (SPOUSE/PARTNER/PARENT/CHILD/SIBLING/OTHER).

### GET /employee/nextOfKin
Query params: `employeeId`
### GET /employee/nextOfKin/{id}
### PUT /employee/nextOfKin/{id}

## Standard Time — POST /employee/standardTime

```json
{"employee": {"id": EMP_ID}, "fromDate": "YYYY-MM-DD", "hoursPerDay": 7.5}
```
Writable fields: `employee` (ref), `fromDate`, `hoursPerDay`.

### GET /employee/standardTime
Query params: `employeeId`
### GET /employee/standardTime/byDate
Query params: `employeeId`, `date`
### GET /employee/standardTime/{id}
### PUT /employee/standardTime/{id}

## Hourly Cost and Rate — POST /employee/hourlyCostAndRate

```json
{"employee": {"id": EMP_ID}, "date": "YYYY-MM-DD", "rate": 500.0, "budgetRate": 450.0, "hourCostRate": 300.0}
```
Writable fields: `employee` (ref), `date`, `rate`, `budgetRate`, `hourCostRate`.

### GET /employee/hourlyCostAndRate
Query params: `employeeId`, `dateFrom`, `dateTo`
### GET /employee/hourlyCostAndRate/{id}
### PUT /employee/hourlyCostAndRate/{id}

## Employee Preferences — PUT /employee/preferences/{id}

Writable fields: `employeeId` (int32), `companyId` (int32), `filterOnProjectParticipant` (boolean), `filterOnProjectManager` (boolean), `language` (string).

### GET /employee/preferences
Query params: `id`, `employeeId`
### PUT /employee/preferences/:changeLanguage
### PUT /employee/preferences/list
### GET /employee/preferences/>loggedInEmployeePreferences

## Search

### GET /employee/searchForEmployeesAndContacts
Wildcard search across employees and contacts. Query params: `query`, `count`

## API Reference

### GET /employee
Find employees corresponding with sent data.
Query params: `id`, `firstName`, `lastName`, `employeeNumber`, `email`, `allowInformationRegistration`, `includeContacts`, `departmentId`, `onlyProjectManagers`, `onlyContacts` (+5 more)

### POST /employee
Create one employee. See Required Fields above. Returns full object with `id`, `version`.

### GET /employee/{id}
Get employee by ID.

### PUT /employee/{id}
Update employee. See Update section above.

### DELETE /employee/{id}
403 Forbidden — employees cannot be deleted.

### GET /employee/category
Query params: `id`, `name`, `number`, `query`

### POST /employee/category
EmployeeCategory writable fields: `displayName`, `name`, `number`, `description`

### DELETE /employee/category/{id}
### GET /employee/category/{id}
### PUT /employee/category/{id}

### GET /employee/employment
Query params: `employeeId`

### POST /employee/employment
See Employment Sub-resource above.

### GET /employee/employment/details
Query params: `employmentId`

### POST /employee/employment/details
See Employment Details above.

### GET /employee/employment/details/{id}
### PUT /employee/employment/details/{id}

### Lookup endpoints (enum-like reference data)
- `GET /employee/employment/employmentType` — all employment type IDs
- `GET /employee/employment/employmentType/employmentEndReasonType` — end reason types
- `GET /employee/employment/employmentType/employmentFormType` — employment form types
- `GET /employee/employment/employmentType/maritimeEmploymentType` — maritime types (query param: `type` **(required)**)
- `GET /employee/employment/employmentType/salaryType` — salary types
- `GET /employee/employment/employmentType/scheduleType` — schedule types
- `GET /employee/employment/remunerationType` — remuneration types
- `GET /employee/employment/workingHoursScheme` — working hours schemes
- `GET /employee/employment/occupationCode` — profession codes (query params: `id`, `nameNO`, `code`)
- `GET /employee/employment/leaveOfAbsence` — query params: `employmentIds`, `date`, `minPercentage`, `maxPercentage`
- `POST /employee/employment/leaveOfAbsence` — LeaveOfAbsence fields: `employment`, `startDate`, `endDate`, `percentage`, `isWageDeduction`, `type`
- `POST /employee/employment/leaveOfAbsence/list` — create multiple
- `GET /employee/employment/leaveOfAbsence/{id}`
- `PUT /employee/employment/leaveOfAbsence/{id}`
- `GET /employee/employment/leaveOfAbsenceType` — all leave of absence type IDs

### Entitlement endpoints
- `GET /employee/entitlement` — query params: `employeeId`
- `GET /employee/entitlement/{id}`
- `GET /employee/entitlement/client` — [BETA] client entitlements
- `PUT /employee/entitlement/:grantEntitlementsByTemplate` — query params: `employeeId` **(required)**, `template` **(required)**
- `PUT /employee/entitlement/:grantClientEntitlementsByTemplate` — query params: `employeeId` **(required)**, `customerId` **(required)**, `template` **(required)**

### Batch operations
- `POST /employee/list` — create multiple employees
- `DELETE /employee/category/list` — query params: `ids` **(required)**
- `POST /employee/category/list` — create multiple categories
- `PUT /employee/category/list` — update multiple categories
