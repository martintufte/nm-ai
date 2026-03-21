# Invoice (+ Order + OrderLine)

## Dependencies
- **Customer** must exist
- **Product** must exist (for order lines)

## Required Fields — POST /invoice

| Field | Required? | Notes |
|-------|-----------|-------|
| `invoiceDate` | Yes | ISO date |
| `invoiceDueDate` | Yes | ISO date |
| `customer` | Yes | `{"id": CUST_ID}` |
| `orders` | **Yes (hidden)** | Must be non-empty array. Error: "Listen kan ikke være tom." / "Kan ikke være null." |

Orders within invoice require:

| Field | Required? | Notes |
|-------|-----------|-------|
| `orderDate` | Yes | ISO date |
| `deliveryDate` | **Yes (hidden)** | Not marked required in spec. Error: "orders.deliveryDate: Kan ikke være null." Use same date as orderDate if no specific delivery date. |
| `customer` | Yes | Must match invoice customer |
| `orderLines` | Yes | At least one |

OrderLines within order require:

| Field | Required? | Notes |
|-------|-----------|-------|
| `count` | Yes | quantity |
| `product` | No | `{"id": PROD_ID}` — optional if you set `description` + `unitPriceExcludingVatCurrency` directly |

**Product-free order lines** — you can skip the product lookup/creation entirely:
```json
{"description": "Consulting 11h @ 1850 NOK", "count": 11, "unitPriceExcludingVatCurrency": 1850}
```
This saves a GET or POST call for the product.

Optional invoice fields: `invoiceNumber` (int32, 0 = auto-generate), `kid` (string — KID customer ID number), `comment` (string), `currency` (Currency ref), `voucher` (Voucher ref), `invoiceRemarks` (string — deprecated, use `invoiceRemark`), `invoiceRemark` (InvoiceRemark ref), `paymentTypeId` (int32 — [BETA] prepaid invoice payment type), `paidAmount` (number — [BETA] prepaid amount), `ehfSendStatus` (string — [Deprecated] EHF/Peppol status).

Optional order fields: `number`, `reference`, `contact` (Contact ref), `attn` (Contact ref), `receiverEmail`, `overdueNoticeEmail`, `ourContact` (Contact ref), `ourContactEmployee` (Employee ref), `department` (Department ref), `project` (Project ref), `invoiceComment`, `internalComment`, `currency` (Currency ref), `invoicesDueIn` (int32), `invoicesDueInType` (string), `isShowOpenPostsOnInvoices` (boolean), `isClosed` (boolean), `deliveryAddress` (DeliveryAddress), `deliveryComment`, `isPrioritizeAmountsIncludingVat` (boolean), `orderLineSorting` (string), `orderGroups` ([OrderGroup] inline), `orderLines` ([OrderLine] inline), `markUpOrderLines` (number — markup %), `discountPercentage` (number), `invoiceOnAccountVatHigh` (boolean), `invoiceSMSNotificationNumber` (string), `sendMethodDescription` (string), `preliminaryInvoice` (Invoice ref).

Subscription order fields: `isSubscription` (boolean), `subscriptionDuration` (int32 — months/years), `subscriptionDurationType` (string), `subscriptionPeriodsOnInvoice` (int32), `subscriptionInvoicingTimeInAdvanceOrArrears` (string), `subscriptionInvoicingTime` (int32), `subscriptionInvoicingTimeType` (string), `isSubscriptionAutoInvoicing` (boolean).

Optional order line fields: `description`, `unitCostCurrency` (number), `unitPriceExcludingVatCurrency` (number), `unitPriceIncludingVatCurrency` (number), `currency` (Currency ref), `markup` (number — %), `discount` (number — %), `vatType` (VatType ref), `inventory` (Inventory ref), `inventoryLocation` (InventoryLocation ref), `vendor` (Company ref), `orderGroup` (OrderGroup ref), `sortIndex` (int32), `isSubscription` (boolean), `subscriptionPeriodStart`/`subscriptionPeriodEnd` (string).

## Call-saving Patterns

- **Inline everything in one POST**: Invoice → Orders → OrderLines can all be created in a single `POST /invoice` call. This is the preferred approach — 1 call instead of 3+.
- **POST returns full object** with `id`, `version`, and all nested IDs. Use for subsequent payment/credit note calls.
- **Customer/product IDs from prior creates**: if you just created the customer or product, reuse those IDs directly.
- **Minimum total: 2-4 calls** for a full invoice workflow (customer + product + invoice + payment). Customer/product can be skipped if they already exist.

## Minimum Payload — Full Invoice (1 call)
```json
POST /invoice
{
  "invoiceDate": "YYYY-MM-DD",
  "invoiceDueDate": "YYYY-MM-DD",
  "customer": {"id": CUST_ID},
  "orders": [{
    "orderDate": "YYYY-MM-DD",
    "deliveryDate": "YYYY-MM-DD",
    "customer": {"id": CUST_ID},
    "orderLines": [{
      "product": {"id": PROD_ID},
      "count": 2
    }]
  }]
}
```

## Register Payment — PUT /invoice/{id}/:payment
**Uses QUERY PARAMS, not request body!** Sending JSON body → 422.
```
PUT /invoice/{id}/:payment?paymentDate=YYYY-MM-DD&paymentTypeId=PAY_TYPE_ID&paidAmount=1000.0
```
All three query params required. Send empty body.

Lookup payment types: `GET /invoice/paymentType`

## Create Credit Note — PUT /invoice/{id}/:createCreditNote
**Uses QUERY PARAMS, not request body!**
```
PUT /invoice/{id}/:createCreditNote?date=YYYY-MM-DD&comment=reason
```
`date` required. `comment` optional. Returns a new invoice object (the credit note) with its own ID.

## Delete
`DELETE /invoice/{id}` → **403 Forbidden**. Invoices cannot be deleted. Use credit note to void instead.

## Troubleshooting: Bank Account Number
Bank accounts are part of company setup and are already configured in typical environments. **Do not** proactively GET/PUT bank accounts. If invoice creation fails with "Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer", then do the bank account setup and retry:
```
GET /ledger/account?isBankAccount=true&count=20
PUT /ledger/account/{BANK_ACCOUNT_ID}
{"id": BANK_ACCOUNT_ID, "version": V, "bankAccountNumber": "12345678903"}
```

## Order as Standalone Entity

### POST /order
```json
{"orderDate": "YYYY-MM-DD", "deliveryDate": "YYYY-MM-DD", "customer": {"id": X}}
```
Returns full object with `id`, `version`.

### POST /order/orderline
```json
{"order": {"id": ORDER_ID}, "product": {"id": PROD_ID}, "count": 3}
```

### DELETE /order/{id}
422 if invoices exist ("Ordren kan ikke slettes. Fakturaer er generert."). Orders with invoices are permanent.

## API Reference

### GET /invoice
Query params: `id`, `invoiceDateFrom` **(required)**, `invoiceDateTo` **(required)**, `invoiceNumber`, `kid`, `voucherId`, `customerId`

### POST /invoice
Create invoice with inline orders. Returns full object.

### GET /invoice/{id}
### PUT /invoice/{id}/:payment
Query params: `paymentDate` **(required)**, `paymentTypeId` **(required)**, `paidAmount` **(required)**
### PUT /invoice/{id}/:createCreditNote
Query params: `date` **(required)**, `comment`
### PUT /invoice/{id}/:createReminder
Query params: `type` **(required)**, `date` **(required)**, `dispatchType`, `includeCharge`, `includeInterest`, `smsNumber`
### PUT /invoice/{id}/:send
Query params: `sendType` **(required)**, `overrideEmailAddress`
### GET /invoice/{invoiceId}/pdf
Query params: `download`

### GET /invoice/details
Query params: `id`, `invoiceDateFrom` **(required)**, `invoiceDateTo` **(required)**
### GET /invoice/details/{id}

### GET /invoice/paymentType
Query params: `id`, `description`, `query`
### GET /invoice/paymentType/{id}

### POST /invoice/list
[BETA] Create multiple invoices. Max 100.

### GET /order
Query params: `id`, `number`, `customerId`, `orderDateFrom` **(required)**, `orderDateTo` **(required)**, `isClosed`, `isSubscription`

### POST /order
### POST /order/list — create multiple orders
### GET /order/{id}
### PUT /order/{id}
### DELETE /order/{id}
### PUT /order/{id}/:invoice — Create invoice from order. Query params: `invoiceDate` **(required)**, `sendToCustomer`, `paymentTypeId`, `paidAmount`
### PUT /order/{id}/:approveSubscriptionInvoice — Query params: `invoiceDate` **(required)**
### PUT /order/{id}/:unApproveSubscriptionInvoice
### PUT /order/{id}/:attach — Attach document to order
### PUT /order/:invoiceMultipleOrders — [BETA] Invoice multiple orders to same customer. Query params: `id` **(required)**, `invoiceDate` **(required)**

### POST /order/orderline
### POST /order/orderline/list
### GET /order/orderline/{id}
### PUT /order/orderline/{id}
### DELETE /order/orderline/{id}
### PUT /order/orderline/{id}/:pickLine — Logistics: mark line as picked
### PUT /order/orderline/{id}/:unpickLine — Logistics: unmark picked line
### GET /order/orderline/orderLineTemplate — Query params: `orderId` **(required)**, `productId` **(required)**

### POST /order/orderGroup
OrderGroup writable fields: `order`, `title`, `comment`, `sortIndex`, `orderLines` (inline)
### PUT /order/orderGroup
### DELETE /order/orderGroup/{id}
### GET /order/orderGroup/{id}

### Order document endpoints
- `PUT /order/sendInvoicePreview/{orderId}` — send invoice preview
- `PUT /order/sendOrderConfirmation/{orderId}` — send order confirmation
- `PUT /order/sendPackingNote/{orderId}` — send packing note
- `GET /order/orderConfirmation/{orderId}/pdf` — get order confirmation PDF
- `GET /order/packingNote/{orderId}/pdf` — get packing note PDF

## Ledger Account Reference (see ledger skill for full details)

### GET /ledger/account
Query params: `id`, `number`, `isBankAccount`, `isInactive`

### PUT /ledger/account/{id}
Key fields for invoicing: `bankAccountNumber`, `bankName`, `bankAccountIBAN`, `bankAccountSWIFT`
