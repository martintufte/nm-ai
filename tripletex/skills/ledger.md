# Ledger (Accounts, Postings, Vouchers, VAT, Currency)

## Account — Ledger Accounts

Used for chart of accounts management and bank account setup (required before invoicing).

### POST /ledger/account
Account writable fields: `number` (int32), `name`, `description`, `ledgerType` (string — GENERAL/CUSTOMER/VENDOR/EMPLOYEE/ASSET), `vatType` (VatType ref), `vatLocked` (boolean), `currency` (Currency ref), `isCloseable` (boolean), `isApplicableForSupplierInvoice` (boolean), `requireReconciliation` (boolean), `isInactive` (boolean), `isBankAccount` (boolean), `isInvoiceAccount` (boolean), `bankAccountNumber` (string), `bankAccountCountry` (Country ref), `bankName`, `bankAccountIBAN`, `bankAccountSWIFT`, `saftCode`, `groupingCode`, `displayName`, `requiresDepartment` (boolean), `requiresProject` (boolean), `invoicingDepartment` (Department ref), `department` (Department ref), `quantityType1` (ProductUnit ref), `quantityType2` (ProductUnit ref).

### Bank account setup (required for invoicing)
```
GET /ledger/account?isBankAccount=true&count=20
PUT /ledger/account/{BANK_ACCOUNT_ID}
{"id": BANK_ACCOUNT_ID, "version": V, "bankAccountNumber": "12345678903"}
```
Without a bank account number set, invoice creation fails: "Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer."

### GET /ledger/account
Query params: `id`, `number`, `isBankAccount`, `isInactive`, `isApplicableForSupplierInvoice`, `ledgerType`, `isBalanceAccount`, `saftCode`

### POST /ledger/account/list — create multiple
### PUT /ledger/account/list — update multiple
### DELETE /ledger/account/list — query params: `ids` **(required)**
### GET /ledger/account/{id}
### PUT /ledger/account/{id}
### DELETE /ledger/account/{id}

---

## Posting — Ledger Postings

Read-only lookup of accounting postings. Created indirectly via vouchers.

Posting writable fields (used inside vouchers): `voucher` (ref), `date`, `description`, `account` (Account ref), `amortizationAccount` (Account ref), `amortizationStartDate`/`amortizationEndDate`, `customer` (ref), `supplier` (ref), `employee` (ref), `project` (ref), `product` (ref), `department` (ref), `vatType` (ref), `amount` (number), `amountCurrency` (number), `amountGross` (number), `amountGrossCurrency` (number), `currency` (ref), `closeGroup` (ref), `invoiceNumber`, `termOfPayment`, `row` (int32).

### GET /ledger/posting
Query params: `dateFrom` **(required)**, `dateTo` **(required)**, `openPostings`, `accountId`, `supplierId`, `customerId`, `employeeId`, `departmentId`, `projectId`, `productId` (+more)

### PUT /ledger/posting/:closePostings — close postings
### GET /ledger/posting/openPost
Query params: `date` **(required)**, `accountId`, `supplierId`, `customerId`, `employeeId`, `departmentId`, `projectId`
### GET /ledger/posting/{id}

---

## Voucher

Vouchers are the core accounting documents. Creating a voucher also creates its postings. Only gross amounts are used; amounts should be rounded to 2 decimals.

### POST /ledger/voucher
Voucher writable fields: `date` (string), `description`, `voucherType` (VoucherType ref), `reverseVoucher` (Voucher ref), `postings` ([Posting] — inline), `document` (Document), `attachment` (Document), `externalVoucherNumber` (string — max 70 chars), `ediDocument` (Document), `vendorInvoiceNumber` (string).

```json
POST /ledger/voucher
{
  "date": "YYYY-MM-DD",
  "description": "Payment",
  "postings": [
    {"date": "YYYY-MM-DD", "account": {"id": DEBIT_ACCT}, "amount": 1000.0},
    {"date": "YYYY-MM-DD", "account": {"id": CREDIT_ACCT}, "amount": -1000.0}
  ]
}
```

### GET /ledger/voucher
Query params: `id`, `number`, `numberFrom`, `numberTo`, `typeId`, `dateFrom` **(required)**, `dateTo` **(required)**

### GET /ledger/voucher/{id}
### PUT /ledger/voucher/{id} — update voucher (postings with guiRow==0 are deleted and recreated)
### DELETE /ledger/voucher/{id}

### PUT /ledger/voucher/{id}/:reverse
Reverse a voucher. Query params: `date` **(required)**

### PUT /ledger/voucher/{id}/:sendToInbox
### PUT /ledger/voucher/{id}/:sendToLedger

### GET /ledger/voucher/{id}/options — meta information about operations

### PUT /ledger/voucher/list — update multiple

### GET /ledger/voucher/>externalVoucherNumber — find by external number
Query params: `externalVoucherNumber`
### GET /ledger/voucher/>nonPosted — find non-posted vouchers
Query params: `includeNonApproved` **(required)**
### GET /ledger/voucher/>voucherReception — vouchers in reception

### Voucher attachments
- `POST /ledger/voucher/{voucherId}/attachment` — upload attachment
- `DELETE /ledger/voucher/{voucherId}/attachment` — delete attachment
- `GET /ledger/voucher/{voucherId}/pdf` — get PDF

### Opening balance [BETA]
- `GET /ledger/voucher/openingBalance` — get opening balance voucher
- `POST /ledger/voucher/openingBalance` — create opening balance on date
- `DELETE /ledger/voucher/openingBalance` — delete opening balance
- `GET /ledger/voucher/openingBalance/>correctionVoucher` — get correction voucher

### Historical vouchers [BETA]
- `POST /ledger/voucher/historical/historical` — create historical vouchers
- `POST /ledger/voucher/historical/employee` — create employee from external import
- `PUT /ledger/voucher/historical/:closePostings` — close historical postings
- `PUT /ledger/voucher/historical/:reverseHistoricalVouchers` — delete all historical vouchers

### Import
- `POST /ledger/voucher/importDocument` — upload document to create voucher(s)
- `POST /ledger/voucher/importGbat10` — import GBAT10 (multipart form)

---

## Voucher Type

### GET /ledger/voucherType
Query params: `name`
### GET /ledger/voucherType/{id}

VoucherType writable fields: `name`, `displayName`.

---

## VAT Type

### GET /ledger/vatType
Query params: `id`, `number`, `typeOfVat`, `vatDate`, `isDisabled`

Returns all VAT codes. Common codes: id=1 (input 25%), id=3 (output 25%), etc. **Note:** Most VAT codes are INVALID for products — only use at invoicing level.

### GET /ledger/vatType/{id}
### PUT /ledger/vatType/createRelativeVatType
Query params: `name` **(required)**, `vatTypeId` **(required)**, `percentage` **(required)**

### GET /ledger/vatSettings — company VAT settings
### PUT /ledger/vatSettings — update company VAT settings

---

## Currency

### GET /currency
Query params: `id`, `code`

Use `GET /currency?code=NOK` to find the NOK currency ID.

### GET /currency/{id}
### GET /currency/{id}/rate — exchange rates for currency
### GET /currency/{fromCurrencyID}/exchangeRate — exchange rate from one currency
### GET /currency/{fromCurrencyID}/{toCurrencyID}/exchangeRate — exchange rate between two currencies

---

## Other Ledger Endpoints

### Payment types for outgoing payments [BETA]
- `GET /ledger/paymentTypeOut`
- `POST /ledger/paymentTypeOut`
- `GET /ledger/paymentTypeOut/{id}`
- `PUT /ledger/paymentTypeOut/{id}`
- `DELETE /ledger/paymentTypeOut/{id}`
- `POST /ledger/paymentTypeOut/list`
- `PUT /ledger/paymentTypeOut/list`

### Accounting periods
- `GET /ledger/accountingPeriod` — find periods
- `GET /ledger/accountingPeriod/{id}`

### Annual accounts
- `GET /ledger/annualAccount` — find annual accounts
- `GET /ledger/annualAccount/{id}`

### Close groups
- `GET /ledger/closeGroup` — query params: `dateFrom` **(required)**, `dateTo` **(required)**
- `GET /ledger/closeGroup/{id}`

### Open posts
- `GET /ledger/openPost` — query params: `date` **(required)**, `accountId`, `supplierId`, `customerId`

### Posting rules
- `GET /ledger/postingRules` — posting rules for current company

### Accounting dimensions
- `GET /ledger/accountingDimensionName` — all dimension names
- `POST /ledger/accountingDimensionName` — create user-defined dimension
- `GET /ledger/accountingDimensionName/{id}`
- `PUT /ledger/accountingDimensionName/{id}`
- `DELETE /ledger/accountingDimensionName/{id}`
- `POST /ledger/accountingDimensionValue` — create dimension value
- `PUT /ledger/accountingDimensionValue/list`
- `GET /ledger/accountingDimensionValue/{id}`
- `DELETE /ledger/accountingDimensionValue/{id}`
