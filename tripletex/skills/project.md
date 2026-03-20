# Project

## Dependencies
- **Employee** must exist (as `projectManager`)

## Required Fields — POST /project

| Field | Required? | Notes |
|-------|-----------|-------|
| `name` | Yes | |
| `projectManager` | Yes | `{"id": EMP_ID}` |
| `isInternal` | Yes | boolean |
| `startDate` | **Yes (hidden)** | Not marked required in spec. Error if omitted: "Feltet må fylles ut." |

Optional fields: `number` (auto-generated if NULL), `description`, `department` (Department ref), `mainProject` (Project ref), `endDate`, `customer` (Customer ref), `isClosed`, `isReadyForInvoicing`, `isOffer` (boolean — true=offer, false=project), `isFixedPrice` (boolean — true=fixed price, false=hourly rate), `projectCategory` (ProjectCategory ref), `deliveryAddress` (Address), `boligmappaAddress` (Address), `displayNameFormat` (string — name presentation in overviews), `reference`, `externalAccountsNumber`, `vatType` (VatType ref), `fixedprice` (number — in project's currency), `currency` (Currency ref), `markUpOrderLines` (number — %), `markUpFeesEarned` (number — %), `isPriceCeiling` (boolean), `priceCeilingAmount` (number), `projectHourlyRates` ([ProjectHourlyRate] inline), `participants` ([ProjectParticipant] inline), `projectActivities` ([ProjectActivity] inline), `contact` (Contact ref), `attention` (Contact ref), `invoiceComment`, `preliminaryInvoice` (Invoice ref), `generalProjectActivitiesPerProjectOnly` (boolean), `invoiceDueDate` (int32), `invoiceDueDateType` (string), `invoiceReceiverEmail`, `overdueNoticeEmail`, `accessType` (string — READ/WRITE), `forParticipantsOnly` (boolean), `useProductNetPrice` (boolean), `ignoreCompanyProductDiscountAgreement` (boolean), `invoiceOnAccountVatHigh` (boolean), `accountingDimensionValues` ([AccountingDimensionValue] — [BETA]).

## Call-saving Patterns

- **POST returns full object** with `id`, `version`. No GET needed.
- **Inline participants**: include `"participants": [{"employee": {"id": X}}]` on the POST to add participants in the same call.
- **Inline project activities**: include `"projectActivities": [{"activity": {"id": X}}]` on the POST.
- **Inline hourly rates**: include `"projectHourlyRates": [...]` on the POST.
- If you just created the employee for projectManager, reuse its `id` directly.

## Minimum Payload
```json
POST /project
{"name": "X", "projectManager": {"id": EMP_ID}, "isInternal": true, "startDate": "YYYY-MM-DD"}
```

## Update — PUT /project/{id}
Requires `id` and `version`.
```json
PUT /project/{id}
{"id": X, "version": V, "name": "X", "projectManager": {"id": EMP_ID}, "isInternal": true, "startDate": "YYYY-MM-DD"}
```

## Delete
`DELETE /project/{id}` → 204 (succeeds).

## API Reference

### GET /project
Query params: `id`, `name`, `number`, `isOffer`, `projectManagerId`, `customerAccountManagerId`, `employeeInProjectId`, `departmentId`, `startDateFrom`, `startDateTo` (+7 more)

### POST /project
Add new project. Returns full object.

### GET /project/{id}
### PUT /project/{id}
### DELETE /project/{id}
### DELETE /project (multiple)

### GET /project/number/{number}
Find project by number.

### GET /project/category
Query params: `id`, `name`, `number`, `description`

### POST /project/category
ProjectCategory writable fields: `name`, `number`, `description`, `displayName`

### GET /project/category/{id}
### PUT /project/category/{id}

### POST /project/participant
ProjectParticipant writable fields: `project`, `employee`, `adminAccess`

### POST /project/participant/list
### DELETE /project/participant/list
### GET /project/participant/{id}
### PUT /project/participant/{id}

### POST /project/projectActivity
ProjectActivity writable fields: `activity`, `project`, `startDate`, `endDate`, `isClosed`, `budgetHours`, `budgetHourlyRateCurrency`, `budgetFeeCurrency`

### DELETE /project/projectActivity/{id}
### GET /project/projectActivity/{id}

### GET /project/hourlyRates
Query params: `id`, `projectId`, `type`, `startDateFrom`, `startDateTo`, `showInProjectOrder`

### POST /project/hourlyRates
ProjectHourlyRate writable fields: `project`, `startDate`, `showInProjectOrder`, `hourlyRateModel`, `projectSpecificRates` (inline array), `fixedRate`

### POST /project/hourlyRates/list
### PUT /project/hourlyRates/list
### DELETE /project/hourlyRates/{id}
### GET /project/hourlyRates/{id}
### PUT /project/hourlyRates/{id}

### GET /project/hourlyRates/projectSpecificRates
Query params: `id`, `projectHourlyRateId`, `employeeId`, `activityId`

### POST /project/hourlyRates/projectSpecificRates
ProjectSpecificRate writable fields: `hourlyRate`, `hourlyCostPercentage`, `projectHourlyRate`, `employee`, `activity`

### GET /project/orderline
Query params: `projectId` **(required)**, `isBudget`

### POST /project/orderline
ProjectOrderLine writable fields: `product`, `description`, `count`, `unitCostCurrency`, `unitPriceExcludingVatCurrency`, `currency`, `markup`, `discount`, `vatType`, `project`, `date`, `isChargeable`

### POST /project/orderline/list
### DELETE /project/orderline/{id}
### GET /project/orderline/{id}
### PUT /project/orderline/{id}

### GET /project/subcontract
Query params: `projectId` **(required)**

### POST /project/subcontract
ProjectSubContract writable fields: `project`, `company`, `budgetFeeCurrency`, `budgetExpensesCurrency`, `budgetIncomeCurrency`, `budgetNetAmountCurrency`, `name`, `description`

### GET /project/task
Query params: `projectId` **(required)**

### GET /project/settings
### PUT /project/settings
ProjectSettings has 50+ boolean/string configuration fields including: `approveHourLists`, `approveInvoices`, `markReadyForInvoicing`, `historicalInformation`, `projectForecast`, `budgetOnSubcontracts`, `projectCategories`, `sortOrderProjects`, `autoCloseInvoicedProjects`, `mustApproveRegisteredHours`, `fixedPriceProjectsFeeCalcMethod`, `autoGenerateProjectNumber`, `autoGenerateStartingNumber`, `projectNameScheme`, `projectTypeOfContract`, `projectHourlyRateModel`, `onlyProjectMembersCanRegisterInfo`, `onlyProjectActivitiesTimesheetRegistration`, `resourcePlanning`, `customControlForms`, etc.

### GET /project/>forTimeSheet
Query params: `includeProjectOffers`, `employeeId`, `date`

### Batch/period endpoints
- `DELETE /project/list` — query params: `ids` **(required)**
- `POST /project/list` — create multiple projects
- `PUT /project/list` — update multiple projects
- `POST /project/import` — query params: `fileFormat` **(required)**
- `GET /project/batchPeriod/budgetStatusByProjectIds` — query params: `ids` **(required)**
- `GET /project/batchPeriod/invoicingReserveByProjectIds` — query params: `ids` **(required)**, `dateFrom` **(required)**, `dateTo` **(required)**
- `GET /project/{id}/period/hourlistReport` — query params: `dateFrom` **(required)**, `dateTo` **(required)**
- `GET /project/{id}/period/invoiced` — query params: `dateFrom` **(required)**, `dateTo` **(required)**
- `GET /project/{id}/period/monthlyStatus` — query params: `dateFrom` **(required)**, `dateTo` **(required)**
- `GET /project/{id}/period/overallStatus` — query params: `dateFrom` **(required)**, `dateTo` **(required)**

### Hourly rates batch
- `DELETE /project/hourlyRates/list` — query params: `ids` **(required)**
- `DELETE /project/hourlyRates/deleteByProjectIds` — query params: `ids` **(required)**, `date` **(required)**
- `PUT /project/hourlyRates/updateOrAddHourRates` — query params: `ids` **(required)**
- `DELETE /project/hourlyRates/projectSpecificRates/list` — query params: `ids` **(required)**
- `POST /project/hourlyRates/projectSpecificRates/list`
- `PUT /project/hourlyRates/projectSpecificRates/list`
- `DELETE /project/hourlyRates/projectSpecificRates/{id}`
- `GET /project/hourlyRates/projectSpecificRates/{id}`
- `PUT /project/hourlyRates/projectSpecificRates/{id}`

### Project activity batch
- `DELETE /project/projectActivity/list` — query params: `ids` **(required)**
- `POST /project/projectActivity/list`

### Project orderline
- `GET /project/orderline/orderLineTemplate` — query params: `projectId` **(required)**, `productId` **(required)**

### Subcontract
- `GET /project/subcontract/{id}`
- `PUT /project/subcontract/{id}`
- `DELETE /project/subcontract/{id}`

### Control forms [BETA]
- `GET /project/controlForm` — query params: `projectId` **(required)**
- `GET /project/controlFormType`

### Resource planning [BETA]
- `GET /project/resourcePlanBudget` — query params: `periodStart` **(required)**, `periodEnd` **(required)**, `periodType` **(required)**
