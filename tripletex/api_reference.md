# Tripletex API Reference (Competition Subset)

## customer

### `GET /customer`
Find customers corresponding with sent data.

Query params: `id`, `customerAccountNumber`, `organizationNumber`, `email`, `invoiceEmail`, `customerName`, `phoneNumberMobile`, `isInactive`, `accountManagerId`, `changedSince`

### `POST /customer`
Create customer. Related customer addresses may also be created.

**Customer** writable fields:
  - `name`: string
  - `organizationNumber`: string
  - `globalLocationNumber`: integer(int64)
  - `supplierNumber`: integer(int32)
  - `customerNumber`: integer(int32)
  - `isSupplier`: boolean — Defines if the customer is also a supplier.
  - `isInactive`: boolean
  - `accountManager`: Employee
  - `department`: Department
  - `email`: string
  - `invoiceEmail`: string
  - `overdueNoticeEmail`: string — The email address of the customer where the noticing emails are sent in case ...
  - `bankAccounts`: [string]
  - `phoneNumber`: string
  - `phoneNumberMobile`: string
  - `description`: string
  - `language`: string
  - `displayName`: string
  - `isPrivateIndividual`: boolean
  - `singleCustomerInvoice`: boolean — Enables various orders on one customer invoice.
  - `invoiceSendMethod`: string — Define the invoicing method for the customer.<br>EMAIL: Send invoices as emai...
  - `emailAttachmentType`: string — Define the invoice attachment type for emailing to the customer.<br>LINK: Sen...
  - `postalAddress`: Address
  - `physicalAddress`: Address
  - `deliveryAddress`: DeliveryAddress
  - `category1`: CustomerCategory
  - `category2`: CustomerCategory
  - `category3`: CustomerCategory
  - `invoicesDueIn`: integer(int32) — Number of days/months in which invoices created from this customer is due
  - `invoicesDueInType`: string — Set the time unit of invoicesDueIn. The special case RECURRING_DAY_OF_MONTH e...
  - `currency`: Currency
  - `bankAccountPresentation`: [CompanyBankAccountPresentation]
  - `ledgerAccount`: Account
  - `isFactoring`: boolean — If true; send this customers invoices to factoring (if factoring is turned on...
  - `invoiceSendSMSNotification`: boolean — Is sms-notification on/off
  - `invoiceSMSNotificationNumber`: string — Send SMS-notification to this number. Must be a norwegian phone number
  - `isAutomaticSoftReminderEnabled`: boolean — Has automatic soft reminders enabled for this customer.
  - `isAutomaticReminderEnabled`: boolean — Has automatic reminders enabled for this customer.
  - `isAutomaticNoticeOfDebtCollectionEnabled`: boolean — Has automatic notice of debt collection enabled for this customer.
  - `discountPercentage`: number — Default discount percentage for this customer.
  - `website`: string

### `GET /customer/category`
Find customer/supplier categories corresponding with sent data.

Query params: `id`, `name`, `number`, `description`, `type`

### `POST /customer/category`
Add new customer/supplier category.

**CustomerCategory** writable fields:
  - `name`: string
  - `number`: string
  - `description`: string
  - `type`: integer(int32)
  - `displayName`: string

### `GET /customer/category/{id}`
Find customer/supplier category by ID.

### `PUT /customer/category/{id}`
Update customer/supplier category.

Body: `CustomerCategory` (see above)

### `POST /customer/list`
[BETA] Create multiple customers. Related supplier addresses may also be created.

### `PUT /customer/list`
[BETA] Update multiple customers. Addresses can also be updated.

### `DELETE /customer/{id}`
[BETA] Delete customer by ID

### `GET /customer/{id}`
Get customer by ID.

### `PUT /customer/{id}`
Update customer.

**Note:** Nested objects (e.g. `postalAddress`) require their own `id`/`version` or updates are silently ignored.

Body: `Customer` (see above)

---

## department

### `GET /department`
Find department corresponding with sent data.

Query params: `id`, `name`, `departmentNumber`, `departmentManagerId`, `isInactive`

### `POST /department`
Add new department.

**Department** writable fields:
  - `name`: string
  - `departmentNumber`: string
  - `departmentManager`: Employee
  - `isInactive`: boolean

### `POST /department/list`
Register new departments.

### `PUT /department/list`
Update multiple departments.

### `GET /department/query`
Wildcard search.

Query params: `id`, `query`, `isInactive`

### `DELETE /department/{id}`
Delete department by ID

### `GET /department/{id}`
Get department by ID.

### `PUT /department/{id}`
Update department.

Body: `Department` (see above)

---

## employee

### `GET /employee`
Find employees corresponding with sent data.

Query params: `id`, `firstName`, `lastName`, `employeeNumber`, `email`, `allowInformationRegistration`, `includeContacts`, `departmentId`, `onlyProjectManagers`, `onlyContacts` (+5 more)

### `POST /employee`
Create one employee.

**Note:** `userType` and `department` are required despite not being marked so in the spec.
Minimum NO_ACCESS: `{"firstName":"X","lastName":"Y","userType":"NO_ACCESS","department":{"id":DEPT_ID}}`
Minimum STANDARD: add `"email":"x@y.com"` to the above.
Employment is NOT auto-created; use `"employments":[{"startDate":"YYYY-MM-DD"}]` to inline it.

**Employee** writable fields:
  - `firstName`: string
  - `lastName`: string
  - `employeeNumber`: string
  - `dateOfBirth`: string
  - `email`: string — **required for STANDARD/EXTENDED userType** (not NO_ACCESS)
  - `phoneNumberMobileCountry`: Country
  - `phoneNumberMobile`: string
  - `phoneNumberHome`: string
  - `phoneNumberWork`: string
  - `nationalIdentityNumber`: string
  - `dnumber`: string
  - `internationalId`: InternationalId
  - `bankAccountNumber`: string
  - `iban`: string — IBAN field
  - `bic`: string — Bic (swift) field
  - `creditorBankCountryId`: integer(int32) — Country of creditor bank field
  - `usesAbroadPayment`: boolean — UsesAbroadPayment field. Determines if we should use domestic or abroad remit...
  - `userType`: string — **secretly required.** Values: "STANDARD", "EXTENDED", "NO_ACCESS"
  - `isContact`: boolean — Determines if the employee is a contact (external) in the company.
  - `comments`: string
  - `address`: Address
  - `department`: Department — **secretly required.** Must be `{"id": DEPT_ID}`
  - `employments`: [Employment]
  - `holidayAllowanceEarned`: HolidayAllowanceEarned
  - `employeeCategory`: EmployeeCategory

### `GET /employee/category`
Find employee category corresponding with sent data.

Query params: `id`, `name`, `number`, `query`

### `POST /employee/category`
Create a new employee category.

**EmployeeCategory** writable fields:
  - `displayName`: string
  - `name`: string
  - `number`: string
  - `description`: string

### `DELETE /employee/category/list`
Delete multiple employee categories

Query params: `ids` **(required)**

### `POST /employee/category/list`
Create new employee categories.

### `PUT /employee/category/list`
Update multiple employee categories.

### `DELETE /employee/category/{id}`
Delete employee category by ID

### `GET /employee/category/{id}`
Get employee category by ID.

### `PUT /employee/category/{id}`
Update employee category information.

Body: `EmployeeCategory` (see above)

### `GET /employee/employment`
Find all employments for employee.

Query params: `employeeId`

### `POST /employee/employment`
Create employment.

**Employment** writable fields:
  - `employee`: Employee
  - `employmentId`: string — Existing employment ID used by the current accounting system
  - `startDate`: string
  - `endDate`: string
  - `employmentEndReason`: string — Define the employment end reason.
  - `division`: Division
  - `lastSalaryChangeDate`: string
  - `noEmploymentRelationship`: boolean — Activate pensions and other benefits with no employment relationship.
  - `isMainEmployer`: boolean — Determines if company is main employer for the employee. Default value is tru...
  - `taxDeductionCode`: string — EMPTY - represents that a tax deduction code is not set on the employment. It...
  - `employmentDetails`: [EmploymentDetails]
  - `isRemoveAccessAtEmploymentEnded`: boolean — If true, access to the employee will be removed when the employment ends. <br...
  - `latestSalary`: EmploymentDetails

### `GET /employee/employment/details`
Find all employmentdetails for employment.

Query params: `employmentId`

### `POST /employee/employment/details`
Create employment details.

**EmploymentDetails** writable fields:
  - `employment`: Employment
  - `date`: string
  - `employmentType`: string — Define the employment type.
  - `employmentForm`: string — Define the employment form.
  - `maritimeEmployment`: MaritimeEmployment
  - `remunerationType`: string — Define the remuneration type.
  - `workingHoursScheme`: string — Define the working hours scheme type. If you enter a value for SHIFT WORK, yo...
  - `shiftDurationHours`: number
  - `occupationCode`: OccupationCode
  - `percentageOfFullTimeEquivalent`: number
  - `annualSalary`: number
  - `hourlyWage`: number
  - `payrollTaxMunicipalityId`: Municipality

### `GET /employee/employment/details/{id}`
Find employment details by ID.

### `PUT /employee/employment/details/{id}`
Update employment details.

Body: `EmploymentDetails` (see above)

### `GET /employee/employment/employmentType`
Find all employment type IDs.

### `GET /employee/employment/employmentType/employmentEndReasonType`
Find all employment end reason type IDs.

### `GET /employee/employment/employmentType/employmentFormType`
Find all employment form type IDs.

### `GET /employee/employment/employmentType/maritimeEmploymentType`
Find all maritime employment type IDs.

Query params: `type` **(required)**

### `GET /employee/employment/employmentType/salaryType`
Find all salary type IDs.

### `GET /employee/employment/employmentType/scheduleType`
Find all schedule type IDs.

### `GET /employee/employment/leaveOfAbsence`
Find all leave of absence corresponding with the sent data.

Query params: `employmentIds`, `date`, `minPercentage`, `maxPercentage`

### `POST /employee/employment/leaveOfAbsence`
Create leave of absence.

**LeaveOfAbsence** writable fields:
  - `employment`: Employment
  - `importedLeaveOfAbsenceId`: string — Existing leave of absence ID used by the current accounting system
  - `startDate`: string
  - `endDate`: string
  - `percentage`: number
  - `isWageDeduction`: boolean
  - `type`: string — Define the leave of absence type.

### `POST /employee/employment/leaveOfAbsence/list`
Create multiple leave of absences.

### `GET /employee/employment/leaveOfAbsence/{id}`
Find leave of absence by ID.

### `PUT /employee/employment/leaveOfAbsence/{id}`
Update leave of absence.

Body: `LeaveOfAbsence` (see above)

### `GET /employee/employment/leaveOfAbsenceType`
Find all leave of absence type IDs.

### `GET /employee/employment/occupationCode`
Find all profession codes.

Query params: `id`, `nameNO`, `code`

### `GET /employee/employment/occupationCode/{id}`
Get occupation by ID.

### `GET /employee/employment/remunerationType`
Find all remuneration type IDs.

### `GET /employee/employment/workingHoursScheme`
Find working hours scheme ID.

### `GET /employee/employment/{id}`
Find employment by ID.

### `PUT /employee/employment/{id}`
Update employemnt.

Body: `Employment` (see above)

### `GET /employee/entitlement`
Find all entitlements for user.

Query params: `employeeId`

### `PUT /employee/entitlement/:grantClientEntitlementsByTemplate`
[BETA] Update employee entitlements in client account.

Query params: `employeeId` **(required)**, `customerId` **(required)**, `template` **(required)**

### `PUT /employee/entitlement/:grantEntitlementsByTemplate`
[BETA] Update employee entitlements.

Query params: `employeeId` **(required)**, `template` **(required)**

### `GET /employee/entitlement/client`
[BETA] Find all entitlements at client for user.

Query params: `employeeId`, `customerId`

### `GET /employee/entitlement/{id}`
Get entitlement by ID.

### `GET /employee/hourlyCostAndRate`
Find all hourly cost and rates for employee.

Query params: `employeeId`

### `POST /employee/hourlyCostAndRate`
Create hourly cost and rate.

**HourlyCostAndRate** writable fields:
  - `employee`: Employee
  - `date`: string
  - `rate`: number
  - `budgetRate`: number
  - `hourCostRate`: number

### `GET /employee/hourlyCostAndRate/{id}`
Find hourly cost and rate by ID.

### `PUT /employee/hourlyCostAndRate/{id}`
Update hourly cost and rate.

Body: `HourlyCostAndRate` (see above)

### `POST /employee/list`
Create several employees.

### `GET /employee/nextOfKin`
Find all next of kin for employee.

Query params: `employeeId`

### `POST /employee/nextOfKin`
Create next of kin.

**NextOfKin** writable fields:
  - `employee`: Employee
  - `name`: string
  - `phoneNumber`: string
  - `address`: string
  - `typeOfRelationship`: string — Define the employee's next of kin relationtype.<br>SPOUSE<br>PARTNER<br>PAREN...

### `GET /employee/nextOfKin/{id}`
Find next of kin by ID.

### `PUT /employee/nextOfKin/{id}`
Update next of kin.

Body: `NextOfKin` (see above)

### `GET /employee/preferences`
Find employee preferences corresponding with sent data.

Query params: `id`, `employeeId`

### `PUT /employee/preferences/:changeLanguage`
Change current employees language to the given language

### `GET /employee/preferences/>loggedInEmployeePreferences`
Get employee preferences for current user

### `PUT /employee/preferences/list`
Update multiple employee preferences.

### `PUT /employee/preferences/{id}`
Update employee preferences information.

**EmployeePreferences** writable fields:
  - `employeeId`: integer(int32)
  - `companyId`: integer(int32)
  - `filterOnProjectParticipant`: boolean
  - `filterOnProjectManager`: boolean
  - `language`: string

### `GET /employee/searchForEmployeesAndContacts`
Get employees and contacts by parameters. Include contacts by default.

Query params: `id`, `firstName`, `lastName`, `email`, `includeContacts`, `isInactive`, `hasSystemAccess`, `excludeReadOnly`

### `GET /employee/standardTime`
Find all standard times for employee.

Query params: `employeeId`

### `POST /employee/standardTime`
Create standard time.

**StandardTime** writable fields:
  - `employee`: Employee
  - `fromDate`: string
  - `hoursPerDay`: number

### `GET /employee/standardTime/byDate`
Find standard time for employee by date.

Query params: `employeeId`, `date`

### `GET /employee/standardTime/{id}`
Find standard time by ID.

### `PUT /employee/standardTime/{id}`
Update standard time.

Body: `StandardTime` (see above)

### `GET /employee/{id}`
Get employee by ID.

### `PUT /employee/{id}`
Update employee.

Body: `Employee` (see above)

---

## invoice

### `GET /invoice`
Find invoices corresponding with sent data. Includes charged outgoing invoices only.

Query params: `id`, `invoiceDateFrom` **(required)**, `invoiceDateTo` **(required)**, `invoiceNumber`, `kid`, `voucherId`, `customerId`

### `POST /invoice`
Create invoice. Related Order and OrderLines can be created first, or included as new objects inside the Invoice.

**PREREQUISITE:** Company must have a bank account number set (`PUT /ledger/account/{id}` with `bankAccountNumber`).
`orders` must be non-empty (at least one order with orderLines). Each inline order needs `deliveryDate`.

**Invoice** writable fields:
  - `invoiceNumber`: integer(int32) — If value is set to 0, the invoice number will be generated.
  - `invoiceDate`: string
  - `customer`: Customer
  - `invoiceDueDate`: string
  - `kid`: string — KID - Kundeidentifikasjonsnummer.
  - `comment`: string — Comment text for the specific invoice.
  - `orders`: [Order] — Related orders. Only one order per invoice is supported at the moment.
  - `voucher`: Voucher
  - `currency`: Currency
  - `invoiceRemarks`: string — Deprecated Invoice remarks - please use the 'invoiceRemark' instead.
  - `invoiceRemark`: InvoiceRemark
  - `paymentTypeId`: integer(int32) — [BETA] Optional. Used to specify payment type for prepaid invoices. Payment t...
  - `paidAmount`: number — [BETA] Optional. Used to specify the prepaid amount of the invoice. The paid ...
  - `ehfSendStatus`: string — [Deprecated] EHF (Peppol) send status. This only shows status for historic EHFs.

### `GET /invoice/details`
Find ProjectInvoiceDetails corresponding with sent data.

Query params: `id`, `invoiceDateFrom` **(required)**, `invoiceDateTo` **(required)**

### `GET /invoice/details/{id}`
Get ProjectInvoiceDetails by ID.

### `POST /invoice/list`
[BETA] Create multiple invoices. Max 100 at a time.

### `GET /invoice/paymentType`
Find payment type corresponding with sent data.

Query params: `id`, `description`, `query`

### `GET /invoice/paymentType/{id}`
Get payment type by ID.

### `GET /invoice/{id}`
Get invoice by ID.

### `PUT /invoice/{id}/:createCreditNote`
Creates a new Invoice representing a credit memo that nullifies the given invoice. Updates this invoice and any pre-existing inverse invoice.

**Uses QUERY PARAMS, not request body!** `?date=YYYY-MM-DD&comment=reason`
`date` required, `comment` optional. Returns a new invoice object (the credit note).

Query params: `date` **(required)**

### `PUT /invoice/{id}/:createReminder`
Create invoice reminder and sends it by the given dispatch type. Supports the reminder types SOFT_REMINDER, REMINDER and NOTICE_OF_DEBT_COLLECTION. DispatchType NETS_PRINT must have type NOTICE_OF_DEBT_COLLECTION. SMS and NETS_PRINT must be activated prior to usage in the API.

Query params: `type` **(required)**, `date` **(required)**

### `PUT /invoice/{id}/:payment`
Update invoice. The invoice is updated with payment information. The amount is in the invoice’s currency.

**Uses QUERY PARAMS, not request body!** `?paymentDate=YYYY-MM-DD&paymentTypeId=X&paidAmount=1000.0`
All three query params are required. Send empty body.

Query params: `paymentDate` **(required)**, `paymentTypeId` **(required)**, `paidAmount` **(required)**

### `PUT /invoice/{id}/:send`
Send invoice by ID and sendType. Optionally override email recipient.

Query params: `sendType` **(required)**

### `GET /invoice/{invoiceId}/pdf`
Get invoice document by invoice ID.

Query params: `download`

---

## ledger

### `GET /ledger`
Get ledger (hovedbok).

**Aggregated ledger (hovedbok).** Returns per-account totals (`sumAmount`, `closingBalance`) for a date range.
Use this instead of `GET /ledger/posting` when you need account-level totals — one call replaces scanning all postings.
Supports `fields` filter, e.g. `fields=account(number,name),sumAmount,closingBalance` for compact output.

Query params: `dateFrom` **(required)**, `dateTo` **(required)**, `openPostings`, `accountId`, `supplierId`, `customerId`, `employeeId`, `departmentId`, `projectId`, `productId` (+3 more)

---

## ledger/account

### `GET /ledger/account`
Find accounts corresponding with sent data.

Query params: `id`, `number`, `isBankAccount`, `isInactive`, `isApplicableForSupplierInvoice`, `ledgerType`, `isBalanceAccount`, `saftCode`

### `POST /ledger/account`
Create a new account.

**Account** writable fields:
  - `number`: integer(int32)
  - `name`: string
  - `description`: string
  - `ledgerType`: string — Supported ledger types, default is GENERAL. Only available for customers with...
  - `vatType`: VatType
  - `vatLocked`: boolean — True if all entries on this account must have the vat type given by vatType.
  - `currency`: Currency
  - `isCloseable`: boolean — True if it should be possible to close entries on this account and it is poss...
  - `isApplicableForSupplierInvoice`: boolean — True if this account is applicable for supplier invoice registration.
  - `requireReconciliation`: boolean — True if this account must be reconciled before the accounting period closure.
  - `isInactive`: boolean — Inactive accounts will not show up in UI lists.
  - `isBankAccount`: boolean
  - `isInvoiceAccount`: boolean
  - `bankAccountNumber`: string
  - `bankAccountCountry`: Country
  - `bankName`: string
  - `bankAccountIBAN`: string
  - `bankAccountSWIFT`: string
  - `saftCode`: string — SAF-T 1.0 standard account ID for account. It will be given a default value b...
  - `groupingCode`: string — SAF-T 1.3 groupingCode for the account. It will be given a default value base...
  - `displayName`: string
  - `requiresDepartment`: boolean — Posting against this account requires department.
  - `requiresProject`: boolean — Posting against this account requires project.
  - `invoicingDepartment`: Department
  - `isPostingsExist`: boolean
  - `quantityType1`: ProductUnit
  - `quantityType2`: ProductUnit
  - `department`: Department

### `DELETE /ledger/account/list`
Delete multiple accounts.

Query params: `ids` **(required)**

### `POST /ledger/account/list`
Create several accounts.

### `PUT /ledger/account/list`
Update multiple accounts.

### `DELETE /ledger/account/{id}`
Delete account.

### `GET /ledger/account/{id}`
Get account by ID.

### `PUT /ledger/account/{id}`
Update account.

Body: `Account` (see above)

---

## ledger/accountingDimensionName

### `GET /ledger/accountingDimensionName`
Get all accounting dimension names.

Query params: `activeOnly`

### `POST /ledger/accountingDimensionName`
Create a new free (aka 'user defined') accounting dimension

**Body:** `{"dimensionName": "<name>"}`. Returns created object with `dimensionIndex` (1, 2, or 3).

**AccountingDimensionName** writable fields:
  - `dimensionName`: string — The name of the dimension.
  - `description`: string — The description of the dimension.
  - `active`: boolean — Indicates if the dimension is active.

### `DELETE /ledger/accountingDimensionName/{id}`
Delete an accounting dimension name by ID

### `GET /ledger/accountingDimensionName/{id}`
Get a single accounting dimension name by ID

### `PUT /ledger/accountingDimensionName/{id}`
Update an accounting dimension

Body: `AccountingDimensionName` (see above)

---

## ledger/accountingDimensionValue

### `POST /ledger/accountingDimensionValue`
Create a new value for one of the free (aka 'user defined') accounting dimensions

**Body:** `{"displayName": "<value name>", "dimensionIndex": <1|2|3>}`. Use `dimensionIndex` from the parent dimension name.

**AccountingDimensionValue** writable fields:
  - `displayName`: string — The name of the value.
  - `dimensionIndex`: integer(int32) — The index of the dimension this value belongs to.
  - `active`: boolean — Indicates if the value is active.
  - `number`: string — The number of the value, which can consist of letters and numbers.
  - `showInVoucherRegistration`: boolean — Indicates if the value should be shown in voucher registration.
  - `position`: integer(int32) — The position of the value in the list of values for the dimension.

### `PUT /ledger/accountingDimensionValue/list`
Update accounting dimension values

### `DELETE /ledger/accountingDimensionValue/{id}`
Delete an accounting dimension value.  Values that have been used in postings can not be deleted.

### `GET /ledger/accountingDimensionValue/{id}`
Find accounting dimension values by ID.

---

## ledger/posting

### `GET /ledger/posting`
Find postings corresponding with sent data.

Query params: `dateFrom` **(required)**, `dateTo` **(required)**, `openPostings`, `accountId`, `supplierId`, `customerId`, `employeeId`, `departmentId`, `projectId`, `productId` (+6 more)

### `PUT /ledger/posting/:closePostings`
Close postings.

### `GET /ledger/posting/openPost`
Find open posts corresponding with sent data.

Query params: `date` **(required)**, `accountId`, `supplierId`, `customerId`, `employeeId`, `departmentId`, `projectId`, `productId`, `accountNumberFrom`, `accountNumberTo` (+3 more)

### `GET /ledger/posting/{id}`
Find postings by ID.

---

## ledger/voucher

### `GET /ledger/voucher`
Find vouchers corresponding with sent data.

Query params: `id`, `number`, `numberFrom`, `numberTo`, `typeId`, `dateFrom` **(required)**, `dateTo` **(required)**

### `POST /ledger/voucher`
Add new voucher. IMPORTANT: Also creates postings. Only the gross amounts will be used. Amounts should be rounded to 2 decimals.

**Voucher** writable fields:
  - `date`: string
  - `description`: string
  - `voucherType`: VoucherType
  - `reverseVoucher`: Voucher
  - `postings`: [Posting]
  - `document`: Document
  - `attachment`: Document
  - `externalVoucherNumber`: string — External voucher number. Maximum 70 characters.
  - `ediDocument`: Document
  - `vendorInvoiceNumber`: string — Vendor invoice number.

### `GET /ledger/voucher/>externalVoucherNumber`
Find vouchers based on the external voucher number.

Query params: `externalVoucherNumber`

### `GET /ledger/voucher/>nonPosted`
Find non-posted vouchers.

Query params: `dateFrom`, `dateTo`, `includeNonApproved` **(required)**, `changedSince`

### `GET /ledger/voucher/>voucherReception`
Find vouchers in voucher reception.

Query params: `dateFrom`, `dateTo`, `searchText`

### `PUT /ledger/voucher/historical/:closePostings`
[BETA] Close postings.

### `PUT /ledger/voucher/historical/:reverseHistoricalVouchers`
[BETA] Deletes all historical vouchers. Requires the "All vouchers" and "Advanced Voucher" permissions.

### `POST /ledger/voucher/historical/employee`
[BETA] Create one employee, based on import from external system. Validation is less strict, ie. employee department isn't required.

Body: `Employee` (see above)

### `POST /ledger/voucher/historical/historical`
API endpoint for creating historical vouchers. These are vouchers created outside Tripletex, and should be from closed accounting years. The intended usage is to get access to historical transcations in Tripletex. Also creates postings. All amount fields in postings will be used. VAT postings must be included, these are not generated automatically like they are for normal vouchers in Tripletex. Requires the \"All vouchers\" and \"Advanced Voucher\" permissions.

### `POST /ledger/voucher/historical/{voucherId}/attachment`
Upload attachment to voucher. If the voucher already has an attachment the content will be appended to the existing attachment as new PDF page(s). Valid document formats are PDF, PNG, JPEG and TIFF. Non PDF formats will be converted to PDF. Send as multipart form.

### `POST /ledger/voucher/importDocument`
Upload a document to create one or more vouchers. Valid document formats are PDF, PNG, JPEG and TIFF. EHF/XML is possible with agreement with Tripletex. Send as multipart form.

### `POST /ledger/voucher/importGbat10`
Import GBAT10. Send as multipart form.

### `PUT /ledger/voucher/list`
Update multiple vouchers. Postings with guiRow==0 will be deleted and regenerated.

### `DELETE /ledger/voucher/openingBalance`
[BETA] Delete the opening balance. The correction voucher will also be deleted

### `GET /ledger/voucher/openingBalance`
[BETA] Get the voucher for the opening balance.

### `POST /ledger/voucher/openingBalance`
[BETA] Add an opening balance on the given date.  All movements before this date will be 'zeroed out' in a separate correction voucher. The opening balance must have the first day of a month as the date, and it's also recommended to have the first day of the year as the date. If the postings provided don't balance the voucher, the difference will automatically be posted to a help account

**OpeningBalance** writable fields:
  - `voucherDate`: string — The date for the opening balance
  - `balancePostings`: [OpeningBalanceBalancePosting] — Balance postings
  - `customerPostings`: [OpeningBalanceCustomerPosting] — Postings in the customer sub ledger
  - `supplierPostings`: [OpeningBalanceSupplierPosting] — Postings in the supplier sub ledger
  - `employeePostings`: [OpeningBalanceEmployeePosting] — Postings in the employee sub ledger

### `GET /ledger/voucher/openingBalance/>correctionVoucher`
[BETA] Get the correction voucher for the opening balance.

### `DELETE /ledger/voucher/{id}`
Delete voucher by ID.

### `GET /ledger/voucher/{id}`
Get voucher by ID.

### `PUT /ledger/voucher/{id}`
Update voucher. Postings with guiRow==0 will be deleted and regenerated.

Body: `Voucher` (see above)

### `PUT /ledger/voucher/{id}/:reverse`
Reverses the voucher, and returns the reversed voucher. Supports reversing most voucher types, except salary transactions.

Query params: `date` **(required)**

### `PUT /ledger/voucher/{id}/:sendToInbox`
Send voucher to inbox.

### `PUT /ledger/voucher/{id}/:sendToLedger`
Send voucher to ledger.

### `GET /ledger/voucher/{id}/options`
Returns a data structure containing meta information about operations that are available for this voucher. Currently only implemented for DELETE: It is possible to check if the voucher is deletable.

### `DELETE /ledger/voucher/{voucherId}/attachment`
Delete attachment.

### `POST /ledger/voucher/{voucherId}/attachment`
Upload attachment to voucher. If the voucher already has an attachment the content will be appended to the existing attachment as new PDF page(s). Valid document formats are PDF, PNG, JPEG and TIFF. Non PDF formats will be converted to PDF. Send as multipart form.

### `GET /ledger/voucher/{voucherId}/pdf`
Get PDF representation of voucher by ID.

### `POST /ledger/voucher/{voucherId}/pdf/{fileName}`
[DEPRECATED] Use POST ledger/voucher/{voucherId}/attachment instead.

---

## order

### `GET /order`
Find orders corresponding with sent data.

Query params: `id`, `number`, `customerId`, `orderDateFrom` **(required)**, `orderDateTo` **(required)**, `deliveryComment`, `isClosed`, `isSubscription`

### `POST /order`
Create order.

**Note:** When used inside an invoice, `deliveryDate` is secretly required on each order.

**Order** writable fields:
  - `customer`: Customer
  - `contact`: Contact
  - `attn`: Contact
  - `receiverEmail`: string
  - `overdueNoticeEmail`: string
  - `number`: string
  - `reference`: string
  - `ourContact`: Contact
  - `ourContactEmployee`: Employee
  - `department`: Department
  - `orderDate`: string
  - `project`: Project
  - `invoiceComment`: string — Comment to be displayed in the invoice based on this order. Can be also found...
  - `internalComment`: string — Internal comment to be displayed in order.
  - `currency`: Currency
  - `invoicesDueIn`: integer(int32) — Number of days/months in which invoices created from this order is due
  - `status`: string — Logistics only
  - `invoicesDueInType`: string — Set the time unit of invoicesDueIn. The special case RECURRING_DAY_OF_MONTH e...
  - `isShowOpenPostsOnInvoices`: boolean — Show account statement - open posts on invoices created from this order
  - `isClosed`: boolean — Denotes if this order is closed. A closed order can no longer be invoiced unl...
  - `deliveryDate`: string
  - `deliveryAddress`: DeliveryAddress
  - `deliveryComment`: string
  - `isPrioritizeAmountsIncludingVat`: boolean
  - `orderLineSorting`: string
  - `orderGroups`: [OrderGroup] — Order line groups
  - `orderLines`: [OrderLine] — Order lines tied to the order. New OrderLines may be embedded here, in some e...
  - `isSubscription`: boolean — If true, the order is a subscription, which enables periodical invoicing of o...
  - `subscriptionDuration`: integer(int32) — Number of months/years the subscription shall run
  - `subscriptionDurationType`: string — The time unit of subscriptionDuration
  - `subscriptionPeriodsOnInvoice`: integer(int32) — Number of periods on each invoice
  - `subscriptionInvoicingTimeInAdvanceOrArrears`: string — Invoicing in advance/in arrears
  - `subscriptionInvoicingTime`: integer(int32) — Number of days/months invoicing in advance/in arrears
  - `subscriptionInvoicingTimeType`: string — The time unit of subscriptionInvoicingTime
  - `isSubscriptionAutoInvoicing`: boolean — Automatic invoicing. Starts when the subscription is approved
  - `preliminaryInvoice`: Invoice
  - `sendMethodDescription`: string — Description of how this invoice will be sent
  - `invoiceOnAccountVatHigh`: boolean — Is the on account(a konto) amounts including vat
  - `invoiceSMSNotificationNumber`: string — The phone number of the receiver of sms notifications. Must be a norwegian ph...
  - `markUpOrderLines`: number — Set mark-up (%) for order lines.
  - `discountPercentage`: number — Default discount percentage for order lines.

### `PUT /order/:invoiceMultipleOrders`
[BETA] Charges a single customer invoice from multiple orders. The orders must be to the same customer, currency, due date, receiver email, attn. and smsNotificationNumber

Query params: `id` **(required)**, `invoiceDate` **(required)**

### `POST /order/list`
[BETA] Create multiple Orders with OrderLines. Max 100 at a time.

### `GET /order/orderConfirmation/{orderId}/pdf`
Get PDF representation of order by ID.

Query params: `download`

### `GET /order/orderGroup`
Find orderGroups corresponding with sent data.

Query params: `ids`, `orderIds`

### `POST /order/orderGroup`
[Beta] Post orderGroup.

**OrderGroup** writable fields:
  - `order`: Order
  - `title`: string
  - `comment`: string
  - `sortIndex`: integer(int32) — Defines the presentation order of the orderGroups. Does not need to be, and i...
  - `orderLines`: [OrderLine] — Order lines belonging to the OrderGroup. Order lines that does not belong to ...

### `PUT /order/orderGroup`
[Beta] Put orderGroup.

Body: `OrderGroup` (see above)

### `DELETE /order/orderGroup/{id}`
Delete orderGroup by ID.

### `GET /order/orderGroup/{id}`
Get orderGroup by ID. A orderGroup is a way to group orderLines, and add comments and subtotals

### `POST /order/orderline`
Create order line. When creating several order lines, use /list for better performance.

**OrderLine** writable fields:
  - `product`: Product
  - `inventory`: Inventory
  - `inventoryLocation`: InventoryLocation
  - `description`: string
  - `count`: number
  - `unitCostCurrency`: number — Unit price purchase (cost) excluding VAT in the order's currency
  - `unitPriceExcludingVatCurrency`: number — Unit price of purchase excluding VAT in the order's currency. If only unit pr...
  - `currency`: Currency
  - `markup`: number — Markup given as a percentage (%)
  - `discount`: number — Discount given as a percentage (%)
  - `vatType`: VatType
  - `vendor`: Company
  - `order`: Order
  - `unitPriceIncludingVatCurrency`: number — Unit price of purchase including VAT in the order's currency. If only unit pr...
  - `isSubscription`: boolean
  - `subscriptionPeriodStart`: string
  - `subscriptionPeriodEnd`: string
  - `orderGroup`: OrderGroup
  - `sortIndex`: integer(int32) — Defines the presentation order of the lines. Does not need to be, and is ofte...
  - `isPicked`: boolean — Only used for Logistics customers who activated the available inventory funct...
  - `pickedDate`: string — Only used for Logistics customers who activated the available inventory funct...
  - `orderedQuantity`: number — Only used for Logistics customers who activated the Backorder functionality. ...
  - `isCharged`: boolean — Flag indicating whether the order line is charged or not.

### `POST /order/orderline/list`
Create multiple order lines.

### `GET /order/orderline/orderLineTemplate`
[BETA] Get order line template from order and product

Query params: `orderId` **(required)**, `productId` **(required)**

### `DELETE /order/orderline/{id}`
[BETA] Delete order line by ID.

### `GET /order/orderline/{id}`
Get order line by ID.

### `PUT /order/orderline/{id}`
[BETA] Put order line

Body: `OrderLine` (see above)

### `PUT /order/orderline/{id}/:pickLine`
[BETA] Pick order line. This is only available for customers who have Logistics and who activated the available inventory functionality.

### `PUT /order/orderline/{id}/:unpickLine`
[BETA] Unpick order line.This is only available for customers who have Logistics and who activated the available inventory functionality.

### `GET /order/packingNote/{orderId}/pdf`
Get PDF representation of packing note by ID.

Query params: `type`, `download`

### `PUT /order/sendInvoicePreview/{orderId}`
Send Invoice Preview to customer by email.

### `PUT /order/sendOrderConfirmation/{orderId}`
Send Order Confirmation to customer by email.

### `PUT /order/sendPackingNote/{orderId}`
Send Packing Note to customer by email.

### `DELETE /order/{id}`
Delete order.

**Returns 422 if invoices exist.** Orders with invoices are permanent.

### `GET /order/{id}`
Get order by ID.

### `PUT /order/{id}`
Update order.

Body: `Order` (see above)

### `PUT /order/{id}/:approveSubscriptionInvoice`
To create a subscription invoice, first create a order with the subscription enabled, then approve it with this method. This approves the order for subscription invoicing.

Query params: `invoiceDate` **(required)**

### `PUT /order/{id}/:attach`
Attach document to specified order ID.

### `PUT /order/{id}/:invoice`
Create new invoice or subscription invoice from order.

Query params: `invoiceDate` **(required)**

### `PUT /order/{id}/:unApproveSubscriptionInvoice`
Unapproves the order for subscription invoicing.

---

## product

### `GET /product`
Find products corresponding with sent data.

Query params: `number`, `ids`, `productNumber`, `name`, `ean`, `isInactive`, `isStockItem`, `isSupplierProduct`, `supplierId`, `currencyId` (+10 more)

### `POST /product`
Create new product.

**Note:** Product names must be unique. Omit `vatType` — most VAT codes are invalid for products.
`priceIncludingVatCurrency` does NOT auto-calculate excl price; always set `priceExcludingVatCurrency` explicitly.

**Product** writable fields:
  - `name`: string
  - `number`: string
  - `description`: string
  - `orderLineDescription`: string
  - `ean`: string
  - `costExcludingVatCurrency`: number — Price purchase (cost) excluding VAT in the product's currency
  - `expenses`: number
  - `priceExcludingVatCurrency`: number — Price of purchase excluding VAT in the product's currency
  - `priceIncludingVatCurrency`: number — Price of purchase including VAT in the product's currency
  - `isInactive`: boolean
  - `discountGroup`: DiscountGroup
  - `productUnit`: ProductUnit
  - `isStockItem`: boolean
  - `vatType`: VatType
  - `currency`: Currency
  - `department`: Department
  - `account`: Account
  - `supplier`: Supplier
  - `resaleProduct`: Product
  - `isDeletable`: boolean — For performance reasons, field is deprecated and it will always return false.
  - `hasSupplierProductConnected`: boolean
  - `weight`: number
  - `weightUnit`: string
  - `volume`: number
  - `volumeUnit`: string
  - `hsnCode`: string
  - `image`: Document
  - `mainSupplierProduct`: SupplierProduct
  - `minStockLevel`: number — Minimum available stock level for the product. Applicable only to stock items...

### `GET /product/discountGroup`
Find discount groups corresponding with sent data.

Query params: `id`, `name`, `number`

### `GET /product/discountGroup/{id}`
Get discount group by ID.

### `GET /product/external`
[BETA] Find external products corresponding with sent data. The sorting-field is not in use on this endpoint.

Query params: `name`, `wholesaler`, `organizationNumber`, `elNumber`, `nrfNumber`, `isInactive`

### `GET /product/external/{id}`
[BETA] Get external product by ID.

### `GET /product/group`
Find product group with sent data. Only available for Logistics Basic.

Query params: `id`, `name`, `query`

### `POST /product/group`
Create new product group. Only available for Logistics Basic.

**ProductGroup** writable fields:
  - `name`: string — Product group name
  - `parentGroup`: ProductGroup

### `DELETE /product/group/list`
Delete multiple product groups. Only available for Logistics Basic.

Query params: `ids` **(required)**

### `POST /product/group/list`
Add multiple products groups. Only available for Logistics Basic.

### `PUT /product/group/list`
Update a list of product groups. Only available for Logistics Basic.

### `GET /product/group/query`
Wildcard search. Only available for Logistics Basic.

Query params: `query`, `name`

### `DELETE /product/group/{id}`
Delete product group. Only available for Logistics Basic.

### `GET /product/group/{id}`
Find product group by ID. Only available for Logistics Basic.

### `PUT /product/group/{id}`
Update product group. Only available for Logistics Basic.

Body: `ProductGroup` (see above)

### `GET /product/groupRelation`
Find product group relation with sent data. Only available for Logistics Basic.

Query params: `id`, `productId`, `productGroupId`

### `POST /product/groupRelation`
Create new product group relation. Only available for Logistics Basic.

**ProductGroupRelation** writable fields:
  - `product`: Product
  - `productGroup`: ProductGroup

### `DELETE /product/groupRelation/list`
Delete multiple product group relations. Only available for Logistics Basic.

### `POST /product/groupRelation/list`
Add multiple products group relations. Only available for Logistics Basic.

### `DELETE /product/groupRelation/{id}`
Delete product group relation. Only available for Logistics Basic.

### `GET /product/groupRelation/{id}`
Find product group relation by ID. Only available for Logistics Basic.

### `GET /product/inventoryLocation`
Find inventory locations by product ID. Only available for Logistics Basic.

Query params: `productId`, `inventoryId`, `isMainLocation`

### `POST /product/inventoryLocation`
Create new product inventory location. Only available for Logistics Basic.

**ProductInventoryLocation** writable fields:
  - `product`: Product
  - `inventory`: Inventory
  - `inventoryLocation`: InventoryLocation
  - `isMainLocation`: boolean
  - `isInactive`: boolean

### `POST /product/inventoryLocation/list`
Add multiple product inventory locations. Only available for Logistics Basic.

### `PUT /product/inventoryLocation/list`
Update multiple product inventory locations. Only available for Logistics Basic.

### `DELETE /product/inventoryLocation/{id}`
Delete product inventory location. Only available for Logistics Basic.

### `GET /product/inventoryLocation/{id}`
Get inventory location by ID. Only available for Logistics Basic.

### `PUT /product/inventoryLocation/{id}`
Update product inventory location. Only available for Logistics Basic.

Body: `ProductInventoryLocation` (see above)

### `POST /product/list`
Add multiple products.

### `PUT /product/list`
Update a list of products.

### `GET /product/logisticsSettings`
Get logistics settings for the logged in company.

### `PUT /product/logisticsSettings`
Update logistics settings for the logged in company.

**LogisticsSettings** writable fields:
  - `hasWarehouseLocation`: boolean
  - `showOnboardingWizard`: boolean
  - `moduleSuggestedProductNumber`: boolean
  - `suggestedProductNumber`: string
  - `purchaseOrderDefaultComment`: string
  - `moduleBring`: boolean

### `GET /product/productPrice`
Find prices for a product. Only available for Logistics Basic.

Query params: `productId` **(required)**, `fromDate`, `toDate`, `showOnlyLastPrice`

### `GET /product/supplierProduct`
Find products corresponding with sent data.

Query params: `productId`, `resaleIds`, `vendorId`, `query`, `isInactive`, `productGroupId`, `targetCurrencyId`

### `POST /product/supplierProduct`
Create new supplierProduct.

**SupplierProduct** writable fields:
  - `name`: string
  - `number`: string
  - `description`: string
  - `ean`: string
  - `costExcludingVatCurrency`: number — Price purchase (cost) excluding VAT in the product's currency
  - `cost`: number — Price purchase (cost) in the company's currency
  - `priceExcludingVatCurrency`: number — Price of purchase excluding VAT in the product's currency
  - `priceIncludingVatCurrency`: number — Price of purchase including VAT in the product's currency
  - `isInactive`: boolean
  - `productUnit`: ProductUnit
  - `isStockItem`: boolean
  - `vatType`: VatType
  - `currency`: Currency
  - `supplier`: Supplier
  - `resaleProduct`: Product
  - `isMainSupplierProduct`: boolean — This feature is available only in pilot

### `POST /product/supplierProduct/getSupplierProductsByIds`
Find the products by ids. Method was added as a POST because GET request header has a maximum size that we can exceed with customers that a lot of products.

### `POST /product/supplierProduct/list`
Create list of new supplierProduct.

### `PUT /product/supplierProduct/list`
Update a list of supplierProduct.

### `DELETE /product/supplierProduct/{id}`
Delete supplierProduct.

### `GET /product/supplierProduct/{id}`
Get supplierProduct by ID.

### `PUT /product/supplierProduct/{id}`
Update supplierProduct.

Body: `SupplierProduct` (see above)

### `GET /product/unit`
Find product units corresponding with sent data.

Query params: `id`, `name`, `nameShort`, `commonCode`

### `POST /product/unit`
Create new product unit.

**ProductUnit** writable fields:
  - `name`: string
  - `nameEN`: string
  - `nameShort`: string
  - `nameShortEN`: string
  - `commonCode`: string
  - `isDeletable`: boolean

### `POST /product/unit/list`
Create multiple product units.

### `PUT /product/unit/list`
Update list of product units.

### `GET /product/unit/master`
Find product units master corresponding with sent data.

Query params: `id`, `name`, `nameShort`, `commonCode`, `peppolName`, `peppolSymbol`, `isInactive`

### `GET /product/unit/master/{id}`
Get product unit master by ID.

### `GET /product/unit/query`
Wildcard search.

Query params: `query`

### `DELETE /product/unit/{id}`
Delete product unit by ID.

### `GET /product/unit/{id}`
Get product unit by ID.

### `PUT /product/unit/{id}`
Update product unit.

Body: `ProductUnit` (see above)

### `DELETE /product/{id}`
Delete product.

### `GET /product/{id}`
Get product by ID.

### `PUT /product/{id}`
Update product.

Body: `Product` (see above)

### `DELETE /product/{id}/image`
Delete image.

### `POST /product/{id}/image`
Upload image to product. Existing image on product will be replaced if exists

---

## project

### `DELETE /project`
[BETA] Delete multiple projects.

### `GET /project`
Find projects corresponding with sent data.

Query params: `id`, `name`, `number`, `isOffer`, `projectManagerId`, `customerAccountManagerId`, `employeeInProjectId`, `departmentId`, `startDateFrom`, `startDateTo` (+7 more)

### `POST /project`
Add new project.

**Note:** `startDate`, `projectManager`, and `isInternal` are all required despite the spec not marking them.

**Project** writable fields:
  - `name`: string
  - `number`: string — If NULL, a number is generated automatically.
  - `description`: string
  - `projectManager`: Employee
  - `department`: Department
  - `mainProject`: Project
  - `startDate`: string — **secretly required.** ISO date string
  - `endDate`: string
  - `customer`: Customer
  - `isClosed`: boolean
  - `isReadyForInvoicing`: boolean
  - `isInternal`: boolean
  - `isOffer`: boolean — If is Project Offer set to true, if is Project set to false. The default valu...
  - `isFixedPrice`: boolean — Project is fixed price if set to true, hourly rate if set to false.
  - `projectCategory`: ProjectCategory
  - `deliveryAddress`: Address
  - `boligmappaAddress`: Address
  - `displayNameFormat`: string — Defines project name presentation in overviews.
  - `reference`: string
  - `externalAccountsNumber`: string
  - `vatType`: VatType
  - `fixedprice`: number — Fixed price amount, in the project's currency.
  - `currency`: Currency
  - `markUpOrderLines`: number — Set mark-up (%) for order lines.
  - `markUpFeesEarned`: number — Set mark-up (%) for fees earned.
  - `isPriceCeiling`: boolean — Set to true if an hourly rate project has a price ceiling.
  - `priceCeilingAmount`: number — Price ceiling amount, in the project's currency.
  - `projectHourlyRates`: [ProjectHourlyRate] — Project Rate Types tied to the project.
  - `forParticipantsOnly`: boolean — Set to true if only project participants can register information on the project
  - `participants`: [ProjectParticipant] — Link to individual project participants.
  - `contact`: Contact
  - `attention`: Contact
  - `invoiceComment`: string — Comment for project invoices
  - `preliminaryInvoice`: Invoice
  - `generalProjectActivitiesPerProjectOnly`: boolean — Set to true if a general project activity must be linked to project to allow ...
  - `projectActivities`: [ProjectActivity] — Project Activities
  - `invoiceDueDate`: integer(int32) — invoice due date
  - `invoiceDueDateType`: string — Set the time unit of invoiceDueDate. The special case RECURRING_DAY_OF_MONTH ...
  - `invoiceReceiverEmail`: string — Set the project's invoice receiver email. Will override the default invoice r...
  - `overdueNoticeEmail`: string — Set the project's overdue notice email. Will override the default overdue not...
  - `accessType`: string — READ/WRITE access on project
  - `useProductNetPrice`: boolean
  - `ignoreCompanyProductDiscountAgreement`: boolean
  - `invoiceOnAccountVatHigh`: boolean — The on account(a konto) amounts including VAT
  - `accountingDimensionValues`: [AccountingDimensionValue] — [BETA - Requires pilot feature] Free dimensions for the project.

### `GET /project/>forTimeSheet`
Find projects applicable for time sheet registration on a specific day.

Query params: `includeProjectOffers`, `employeeId`, `date`

### `GET /project/batchPeriod/budgetStatusByProjectIds`
Get the budget status for the projects in the specific period.

Query params: `ids` **(required)**

### `GET /project/batchPeriod/invoicingReserveByProjectIds`
Get the invoicing reserve for the projects in the specific period.

Query params: `ids` **(required)**, `dateFrom` **(required)**, `dateTo` **(required)**

### `GET /project/category`
Find project categories corresponding with sent data.

Query params: `id`, `name`, `number`, `description`

### `POST /project/category`
Add new project category.

**ProjectCategory** writable fields:
  - `name`: string
  - `number`: string
  - `description`: string
  - `displayName`: string

### `GET /project/category/{id}`
Find project category by ID.

### `PUT /project/category/{id}`
Update project category.

Body: `ProjectCategory` (see above)

### `GET /project/controlForm`
[BETA] Get project control forms by project ID.

Query params: `projectId` **(required)**

### `GET /project/controlForm/{id}`
[BETA] Get project control form by ID.

### `GET /project/controlFormType`
[BETA] Get project control form types

### `GET /project/controlFormType/{id}`
[BETA] Get project control form type by ID.

### `PUT /project/dynamicControlForm/{id}/:copyFieldValuesFromLastEditedForm`
Into each section in the specified form that only has empty or default values, and copyFieldValuesByDefault set as true in the form's template, copy field values from the equivalent section in the most recently edited control form. Signed or completed forms will not be affected.

### `GET /project/hourlyRates`
Find project hourly rates corresponding with sent data.

Query params: `id`, `projectId`, `type`, `startDateFrom`, `startDateTo`, `showInProjectOrder`

### `POST /project/hourlyRates`
Create a project hourly rate.

**ProjectHourlyRate** writable fields:
  - `project`: Project
  - `startDate`: string
  - `showInProjectOrder`: boolean — Show on contract confirmation/offers
  - `hourlyRateModel`: string — Defines the model used for the hourly rate.
  - `projectSpecificRates`: [ProjectSpecificRate] — Project specific rates if hourlyRateModel is TYPE_PROJECT_SPECIFIC_HOURLY_RAT...
  - `fixedRate`: number — Fixed Hourly rates if hourlyRateModel is TYPE_FIXED_HOURLY_RATE.

### `DELETE /project/hourlyRates/deleteByProjectIds`
Delete project hourly rates by project id.

Query params: `ids` **(required)**, `date` **(required)**

### `DELETE /project/hourlyRates/list`
Delete project hourly rates.

Query params: `ids` **(required)**

### `POST /project/hourlyRates/list`
Create multiple project hourly rates.

### `PUT /project/hourlyRates/list`
Update multiple project hourly rates.

### `GET /project/hourlyRates/projectSpecificRates`
Find project specific rates corresponding with sent data.

Query params: `id`, `projectHourlyRateId`, `employeeId`, `activityId`

### `POST /project/hourlyRates/projectSpecificRates`
Create new project specific rate.

**ProjectSpecificRate** writable fields:
  - `hourlyRate`: number
  - `hourlyCostPercentage`: number
  - `projectHourlyRate`: ProjectHourlyRate
  - `employee`: Employee
  - `activity`: Activity

### `DELETE /project/hourlyRates/projectSpecificRates/list`
Delete project specific rates.

Query params: `ids` **(required)**

### `POST /project/hourlyRates/projectSpecificRates/list`
Create multiple new project specific rates.

### `PUT /project/hourlyRates/projectSpecificRates/list`
Update multiple project specific rates.

### `DELETE /project/hourlyRates/projectSpecificRates/{id}`
Delete project specific rate

### `GET /project/hourlyRates/projectSpecificRates/{id}`
Find project specific rate by ID.

### `PUT /project/hourlyRates/projectSpecificRates/{id}`
Update a project specific rate.

Body: `ProjectSpecificRate` (see above)

### `PUT /project/hourlyRates/updateOrAddHourRates`
Update or add the same project hourly rate from project overview.

Query params: `ids` **(required)**

**HourlyRate** writable fields:
  - `startDate`: string
  - `hourlyRateModel`: string — Defines the model used for the hourly rate.
  - `projectSpecificRates`: [ProjectSpecificRate] — Project specific rates if hourlyRateModel is TYPE_PROJECT_SPECIFIC_HOURLY_RAT...
  - `fixedRate`: number — Fixed Hourly rates if hourlyRateModel is TYPE_FIXED_HOURLY_RATE.

### `DELETE /project/hourlyRates/{id}`
Delete Project Hourly Rate

### `GET /project/hourlyRates/{id}`
Find project hourly rate by ID.

### `PUT /project/hourlyRates/{id}`
Update a project hourly rate.

Body: `ProjectHourlyRate` (see above)

### `POST /project/import`
Upload project import file.

Query params: `fileFormat` **(required)**

### `DELETE /project/list`
[BETA] Delete projects.

Query params: `ids` **(required)**

### `POST /project/list`
[BETA] Register new projects. Multiple projects for different users can be sent in the same request.

### `PUT /project/list`
[BETA] Update multiple projects.

### `GET /project/number/{number}`
Find project by number.

### `GET /project/orderline`
[BETA] Find all order lines for project.

Query params: `projectId` **(required)**, `isBudget`

### `POST /project/orderline`
[BETA] Create order line. When creating several order lines, use /list for better performance.

**ProjectOrderLine** writable fields:
  - `product`: Product
  - `inventory`: Inventory
  - `inventoryLocation`: InventoryLocation
  - `description`: string
  - `count`: number
  - `unitCostCurrency`: number — Unit price purchase (cost) excluding VAT in the order's currency
  - `unitPriceExcludingVatCurrency`: number — Unit price of purchase excluding VAT in the order's currency. If only unit pr...
  - `currency`: Currency
  - `markup`: number — Markup given as a percentage (%)
  - `discount`: number — Discount given as a percentage (%)
  - `vatType`: VatType
  - `vendor`: Company
  - `project`: Project
  - `date`: string
  - `isChargeable`: boolean
  - `invoice`: Invoice
  - `customSortIndex`: integer(int32)
  - `voucher`: Voucher

### `POST /project/orderline/list`
[BETA] Create multiple order lines.

### `GET /project/orderline/orderLineTemplate`
[BETA] Get order line template from project and product

Query params: `projectId` **(required)**, `productId` **(required)**

### `GET /project/orderline/query`
[BETA] Wildcard search.

Query params: `id`, `projectId`, `query`, `isBudget`

### `DELETE /project/orderline/{id}`
Delete order line by ID.

### `GET /project/orderline/{id}`
[BETA] Get order line by ID.

### `PUT /project/orderline/{id}`
[BETA] Update project orderline.

Body: `ProjectOrderLine` (see above)

### `POST /project/participant`
[BETA] Add new project participant.

**ProjectParticipant** writable fields:
  - `project`: Project
  - `employee`: Employee
  - `adminAccess`: boolean

### `DELETE /project/participant/list`
[BETA] Delete project participants.

Query params: `ids` **(required)**

### `POST /project/participant/list`
[BETA] Add new project participant. Multiple project participants can be sent in the same request.

### `GET /project/participant/{id}`
[BETA] Find project participant by ID.

### `PUT /project/participant/{id}`
[BETA] Update project participant.

Body: `ProjectParticipant` (see above)

### `POST /project/projectActivity`
Add project activity.

**ProjectActivity** writable fields:
  - `activity`: Activity
  - `project`: Project
  - `startDate`: string
  - `endDate`: string
  - `isClosed`: boolean
  - `budgetHours`: number — Set budget hours
  - `budgetHourlyRateCurrency`: number — Set budget hourly rate
  - `budgetFeeCurrency`: number — Set budget fee

### `DELETE /project/projectActivity/list`
Delete project activities

Query params: `ids` **(required)**

### `DELETE /project/projectActivity/{id}`
Delete project activity

### `GET /project/projectActivity/{id}`
Find project activity by id

### `GET /project/resourcePlanBudget`
Get resource plan entries in the specified period.

Query params: `projectId`, `periodStart` **(required)**, `periodEnd` **(required)**, `periodType` **(required)**

### `GET /project/settings`
Get project settings of logged in company.

Query params: `useNkode`

### `PUT /project/settings`
Update project settings for company

**ProjectSettings** writable fields:
  - `approveHourLists`: boolean
  - `approveInvoices`: boolean — True if approval and invoicing are separate
  - `markReadyForInvoicing`: boolean
  - `historicalInformation`: boolean
  - `projectForecast`: boolean
  - `budgetOnSubcontracts`: boolean
  - `projectCategories`: boolean
  - `referenceFee`: boolean
  - `sortOrderProjects`: string
  - `autoCloseInvoicedProjects`: boolean
  - `mustApproveRegisteredHours`: boolean
  - `showProjectOrderLinesToAllProjectParticipants`: boolean
  - `hourCostPercentage`: boolean
  - `fixedPriceProjectsFeeCalcMethod`: string
  - `fixedPriceProjectsInvoiceByProgress`: boolean
  - `projectBudgetReferenceFee`: boolean
  - `allowMultipleProjectInvoiceVat`: boolean
  - `standardReinvoicing`: boolean
  - `isCurrentMonthDefaultPeriod`: boolean
  - `showProjectOnboarding`: boolean
  - `autoConnectIncomingOrderlineToProject`: boolean
  - `autoGenerateProjectNumber`: boolean
  - `autoGenerateStartingNumber`: integer(int32)
  - `projectNameScheme`: string
  - `projectTypeOfContract`: string
  - `projectOrderLinesSortOrder`: string
  - `projectHourlyRateModel`: string
  - `onlyProjectMembersCanRegisterInfo`: boolean
  - `onlyProjectActivitiesTimesheetRegistration`: boolean
  - `hourlyRateProjectsWriteUpDown`: boolean
  - `showRecentlyClosedProjectsOnSupplierInvoice`: boolean
  - `defaultProjectContractComment`: string
  - `defaultProjectInvoicingComment`: string
  - `resourcePlanning`: boolean
  - `resourceGroups`: boolean
  - `holidayPlan`: boolean
  - `resourcePlanPeriod`: string
  - `customControlForms`: boolean
  - `controlFormsRequiredForInvoicing`: [ProjectControlFormType] — Control forms required for invoicing
  - `controlFormsRequiredForHourTracking`: [ProjectControlFormType] — Control forms required for hour tracking
  - `dynamicControlFormIdsRequiredForInvoicing`: [integer(int64)] — Dynamic control form ids required for invoicing
  - `dynamicControlFormIdsRequiredForHourTracking`: [integer(int64)] — Dynamic control form ids required for hour tracking
  - `useLoggedInUserEmailOnProjectBudget`: boolean
  - `emailOnProjectBudget`: string
  - `useLoggedInUserEmailOnProjectContract`: boolean
  - `emailOnProjectContract`: string
  - `useLoggedInUserEmailOnDocuments`: boolean
  - `emailOnDocuments`: string
  - `useProductNetPrice`: boolean
  - `isNHOMember`: boolean

### `GET /project/subcontract`
Find project sub-contracts corresponding with sent data.

Query params: `projectId` **(required)**

### `POST /project/subcontract`
Add new project sub-contract.

**Note:** `displayName` is secretly required (422 if omitted). `name` alone is not enough.

**ProjectSubContract** writable fields:
  - `project`: Project
  - `company`: Company
  - `budgetFeeCurrency`: number
  - `budgetExpensesCurrency`: number
  - `budgetIncomeCurrency`: number
  - `budgetNetAmountCurrency`: number
  - `displayName`: string — **secretly required.** String — fails with 422 if omitted
  - `name`: string
  - `description`: string

### `GET /project/subcontract/query`
Wildcard search.

Query params: `id`, `projectId`, `query`

### `DELETE /project/subcontract/{id}`
Delete project sub-contract by ID.

### `GET /project/subcontract/{id}`
Find project sub-contract by ID.

### `PUT /project/subcontract/{id}`
Update project sub-contract.

Body: `ProjectSubContract` (see above)

### `GET /project/task`
Find all tasks for project.

Query params: `projectId` **(required)**

### `GET /project/template/{id}`
Get project template by ID.

### `DELETE /project/{id}`
[BETA] Delete project.

### `GET /project/{id}`
Find project by ID.

### `PUT /project/{id}`
[BETA] Update project.

Body: `Project` (see above)

### `GET /project/{id}/period/budgetStatus`
Get the budget status for the project period

### `GET /project/{id}/period/hourlistReport`
Find hourlist report by project period.

Query params: `dateFrom` **(required)**, `dateTo` **(required)**

### `GET /project/{id}/period/invoiced`
Find invoiced info by project period.

Query params: `dateFrom` **(required)**, `dateTo` **(required)**

### `GET /project/{id}/period/invoicingReserve`
Find invoicing reserve by project period.

Query params: `dateFrom` **(required)**, `dateTo` **(required)**

### `GET /project/{id}/period/monthlyStatus`
Find overall status by project period.

Query params: `dateFrom` **(required)**, `dateTo` **(required)**

### `GET /project/{id}/period/overallStatus`
Find overall status by project period.

Query params: `dateFrom` **(required)**, `dateTo` **(required)**

---

## travelExpense

### `GET /travelExpense`
Find travel expenses corresponding with sent data.

Query params: `employeeId`, `departmentId`, `projectId`, `projectManagerId`, `departureDateFrom`, `returnDateTo`, `state`

### `POST /travelExpense`
Create travel expense.

**Note:** Dates (`departureDate`, `returnDate`) go inside nested `travelDetails`, NOT at top level.
Minimum: `{"employee":{"id":X},"travelDetails":{"departureDate":"...","returnDate":"...","isDayTrip":true}}`

**TravelExpense** writable fields:
  - `attestationSteps`: [AttestationStep]
  - `attestation`: Attestation
  - `project`: Project
  - `employee`: Employee
  - `approvedBy`: Employee
  - `completedBy`: Employee
  - `rejectedBy`: Employee
  - `department`: Department
  - `freeDimension1`: AccountingDimensionValue
  - `freeDimension2`: AccountingDimensionValue
  - `freeDimension3`: AccountingDimensionValue
  - `payslip`: Payslip
  - `vatType`: VatType
  - `paymentCurrency`: Currency
  - `travelDetails`: TravelDetails
  - `voucher`: Voucher
  - `attachment`: Document
  - `isChargeable`: boolean
  - `isFixedInvoicedAmount`: boolean
  - `isMarkupInvoicedPercent`: boolean
  - `isIncludeAttachedReceiptsWhenReinvoicing`: boolean
  - `travelAdvance`: number
  - `fixedInvoicedAmount`: number
  - `markupInvoicedPercent`: number
  - `invoice`: Invoice
  - `title`: string
  - `perDiemCompensations`: [PerDiemCompensation] — Link to individual per diem compensations.
  - `costs`: [Cost] — Link to individual costs.

### `PUT /travelExpense/:approve`
Approve travel expenses.

### `PUT /travelExpense/:copy`
Copy travel expense.

Query params: `id` **(required)**

### `PUT /travelExpense/:createVouchers`
Create vouchers

Query params: `date` **(required)**

### `PUT /travelExpense/:deliver`
Deliver travel expenses.

### `PUT /travelExpense/:unapprove`
Unapprove travel expenses.

### `PUT /travelExpense/:undeliver`
Undeliver travel expenses.

Body: `TravelExpense` (see above)

### `GET /travelExpense/accommodationAllowance`
Find accommodation allowances corresponding with sent data.

Query params: `travelExpenseId`, `rateTypeId`, `rateCategoryId`, `rateFrom`, `rateTo`, `countFrom`, `countTo`, `amountFrom`, `amountTo`, `location` (+1 more)

### `POST /travelExpense/accommodationAllowance`
Create accommodation allowance.

**Note:** `location` is secretly required.

**AccommodationAllowance** writable fields:
  - `travelExpense`: TravelExpense
  - `rateType`: TravelExpenseRate
  - `rateCategory`: TravelExpenseRateCategory
  - `zone`: string
  - `location`: string
  - `address`: string
  - `count`: integer(int32)
  - `rate`: number
  - `amount`: number

### `DELETE /travelExpense/accommodationAllowance/{id}`
Delete accommodation allowance.

### `GET /travelExpense/accommodationAllowance/{id}`
Get travel accommodation allowance by ID.

### `PUT /travelExpense/accommodationAllowance/{id}`
Update accommodation allowance.

Body: `AccommodationAllowance` (see above)

### `GET /travelExpense/cost`
Find costs corresponding with sent data.

Query params: `travelExpenseId`, `vatTypeId`, `currencyId`, `rateFrom`, `rateTo`, `countFrom`, `countTo`, `amountFrom`, `amountTo`, `location` (+1 more)

### `POST /travelExpense/cost`
Create cost.

**Note:** Use `amountCurrencyIncVat` for the amount, NOT `amount` (that field doesn't exist on POST).

**Cost** writable fields:
  - `travelExpense`: TravelExpense
  - `vatType`: VatType
  - `currency`: Currency
  - `costCategory`: TravelCostCategory
  - `paymentType`: TravelPaymentType
  - `category`: string
  - `comments`: string
  - `rate`: number
  - `amountCurrencyIncVat`: number
  - `amountNOKInclVAT`: number
  - `isChargeable`: boolean
  - `date`: string
  - `participants`: [CostParticipant] — Link to individual expense participant.
  - `predictions`: object

### `PUT /travelExpense/cost/list`
Update costs.

### `DELETE /travelExpense/cost/{id}`
Delete cost.

### `GET /travelExpense/cost/{id}`
Get cost by ID.

### `PUT /travelExpense/cost/{id}`
Update cost.

Body: `Cost` (see above)

### `GET /travelExpense/costCategory`
Find cost category corresponding with sent data.

Query params: `id`, `description`, `isInactive`, `showOnEmployeeExpenses`, `query`

### `GET /travelExpense/costCategory/{id}`
Get cost category by ID.

### `POST /travelExpense/costParticipant`
Create participant on cost.

**CostParticipant** writable fields:
  - `displayName`: string
  - `employeeId`: integer(int32) — Optional employee id in case the participant is an employee
  - `cost`: Cost

### `POST /travelExpense/costParticipant/createCostParticipantAdvanced`
Create participant on cost using explicit parameters

Query params: `costId` **(required)**, `employeeId` **(required)**

### `DELETE /travelExpense/costParticipant/list`
Delete cost participants.

### `POST /travelExpense/costParticipant/list`
Create participants on cost.

### `GET /travelExpense/costParticipant/{costId}/costParticipants`
Get cost's participants by costId.

### `DELETE /travelExpense/costParticipant/{id}`
Delete cost participant.

### `GET /travelExpense/costParticipant/{id}`
Get cost participant by ID.

### `POST /travelExpense/drivingStop`
Create mileage allowance driving stop.

**DrivingStop** writable fields:
  - `locationName`: string
  - `latitude`: number
  - `longitude`: number
  - `sortIndex`: integer(int32)
  - `type`: integer(int32)
  - `mileageAllowance`: MileageAllowance

### `DELETE /travelExpense/drivingStop/{id}`
Delete mileage allowance stops.

### `GET /travelExpense/drivingStop/{id}`
Get driving stop by ID.

### `GET /travelExpense/mileageAllowance`
Find mileage allowances corresponding with sent data.

Query params: `travelExpenseId`, `rateTypeId`, `rateCategoryId`, `kmFrom`, `kmTo`, `rateFrom`, `rateTo`, `amountFrom`, `amountTo`, `departureLocation` (+4 more)

### `POST /travelExpense/mileageAllowance`
Create mileage allowance.

**Note:** Passenger supplement is a SEPARATE mileage entry using rate category 744, not a boolean field.

**MileageAllowance** writable fields:
  - `travelExpense`: TravelExpense
  - `rateType`: TravelExpenseRate
  - `rateCategory`: TravelExpenseRateCategory
  - `date`: string
  - `departureLocation`: string
  - `destination`: string
  - `km`: number
  - `rate`: number
  - `amount`: number
  - `isCompanyCar`: boolean
  - `vehicleType`: integer(int32) — The corresponded number for the vehicleType. Default value = 0.
  - `passengerSupplement`: MileageAllowance
  - `trailerSupplement`: MileageAllowance
  - `tollCost`: Cost

### `DELETE /travelExpense/mileageAllowance/{id}`
Delete mileage allowance.

### `GET /travelExpense/mileageAllowance/{id}`
Get mileage allowance by ID.

### `PUT /travelExpense/mileageAllowance/{id}`
Update mileage allowance.

Body: `MileageAllowance` (see above)

### `GET /travelExpense/passenger`
Find passengers corresponding with sent data.

Query params: `mileageAllowance`, `name`

### `POST /travelExpense/passenger`
Create passenger.

**Passenger** writable fields:
  - `name`: string
  - `mileageAllowance`: MileageAllowance

### `DELETE /travelExpense/passenger/list`
Delete passengers.

### `POST /travelExpense/passenger/list`
Create passengers.

### `DELETE /travelExpense/passenger/{id}`
Delete passenger.

### `GET /travelExpense/passenger/{id}`
Get passenger by ID.

### `PUT /travelExpense/passenger/{id}`
Update passenger.

Body: `Passenger` (see above)

### `GET /travelExpense/paymentType`
Find payment type corresponding with sent data.

Query params: `id`, `description`, `isInactive`, `showOnEmployeeExpenses`, `query`

### `GET /travelExpense/paymentType/{id}`
Get payment type by ID.

### `GET /travelExpense/perDiemCompensation`
Find per diem compensations corresponding with sent data.

Query params: `travelExpenseId`, `rateTypeId`, `rateCategoryId`, `overnightAccommodation`, `countFrom`, `countTo`, `rateFrom`, `rateTo`, `amountFrom`, `amountTo` (+5 more)

### `POST /travelExpense/perDiemCompensation`
Create per diem compensation.

**Note:** `location` is secretly required. `count` is number of days (integer), NOT a date range.
`overnightAccommodation`: e.g. `"HOTEL"`, `"NONE"`.

**PerDiemCompensation** writable fields:
  - `travelExpense`: TravelExpense
  - `rateType`: TravelExpenseRate
  - `rateCategory`: TravelExpenseRateCategory
  - `countryCode`: string
  - `travelExpenseZoneId`: integer(int32) — Optional travel expense zone id. If not specified, the value from field zone ...
  - `overnightAccommodation`: string — Set what sort of accommodation was had overnight.
  - `location`: string — **secretly required.**
  - `address`: string
  - `count`: integer(int32)
  - `rate`: number
  - `amount`: number
  - `isDeductionForBreakfast`: boolean
  - `isDeductionForLunch`: boolean
  - `isDeductionForDinner`: boolean

### `DELETE /travelExpense/perDiemCompensation/{id}`
Delete per diem compensation.

### `GET /travelExpense/perDiemCompensation/{id}`
Get per diem compensation by ID.

### `PUT /travelExpense/perDiemCompensation/{id}`
Update per diem compensation.

Body: `PerDiemCompensation` (see above)

### `GET /travelExpense/rate`
Find rates corresponding with sent data.

Query params: `rateCategoryId`, `type`, `isValidDayTrip`, `isValidAccommodation`, `isValidDomestic`, `isValidForeignTravel`, `requiresZone`, `requiresOvernightAccommodation`, `dateFrom`, `dateTo`

### `GET /travelExpense/rate/{id}`
Get travel expense rate by ID.

### `GET /travelExpense/rateCategory`
Find rate categories corresponding with sent data.

Query params: `type`, `name`, `travelReportRateCategoryGroupId`, `ameldingWageCode`, `wageCodeNumber`, `isValidDayTrip`, `isValidAccommodation`, `isValidDomestic`, `requiresZone`, `isRequiresOvernightAccommodation` (+2 more)

### `GET /travelExpense/rateCategory/{id}`
Get travel expense rate category by ID.

### `GET /travelExpense/rateCategoryGroup`
Find rate categoriy groups corresponding with sent data.

Query params: `name`, `isForeignTravel`, `dateFrom`, `dateTo`

### `GET /travelExpense/rateCategoryGroup/{id}`
Get travel report rate category group by ID.

### `GET /travelExpense/settings`
Get travel expense settings of logged in company.

### `GET /travelExpense/zone`
Find travel expense zones corresponding with sent data.

Query params: `id`, `code`, `isDisabled`, `query`, `date`

### `GET /travelExpense/zone/{id}`
Get travel expense zone by ID.

### `DELETE /travelExpense/{id}`
Delete travel expense.

### `GET /travelExpense/{id}`
Get travel expense by ID.

### `PUT /travelExpense/{id}`
Update travel expense.

Body: `TravelExpense` (see above)

### `PUT /travelExpense/{id}/convert`
Convert travel to/from employee expense.

### `DELETE /travelExpense/{travelExpenseId}/attachment`
Delete attachment.

### `GET /travelExpense/{travelExpenseId}/attachment`
Get attachment by travel expense ID.

### `POST /travelExpense/{travelExpenseId}/attachment`
Upload attachment to travel expense.

### `POST /travelExpense/{travelExpenseId}/attachment/list`
Upload multiple attachments to travel expense.

---
