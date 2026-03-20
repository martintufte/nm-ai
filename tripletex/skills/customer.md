# Customer

## Dependencies
None — customer can be created from scratch.

## Required Fields — POST /customer

| Field | Required? | Notes |
|-------|-----------|-------|
| `name` | Yes | Sufficient alone for creation |

All other fields optional: `organizationNumber`, `supplierNumber` (int32), `globalLocationNumber` (int64), `customerNumber` (int32), `email`, `invoiceEmail`, `overdueNoticeEmail`, `phoneNumber`, `phoneNumberMobile`, `description`, `language`, `displayName`, `isPrivateIndividual`, `isSupplier`, `isInactive`, `accountManager` (Employee ref), `department` (Department ref), `postalAddress` (Address), `physicalAddress` (Address), `deliveryAddress` (DeliveryAddress), `category1`/`category2`/`category3` (CustomerCategory refs), `invoicesDueIn` (int32), `invoicesDueInType` (string), `currency` (Currency ref), `bankAccounts` ([string]), `singleCustomerInvoice` (boolean), `invoiceSendMethod` (string — EMAIL/EHF/EFAKTURA/AVTALEGIRO/VIPPS/PAPER/MANUAL), `emailAttachmentType` (string — LINK/ATTACHMENT), `ledgerAccount` (Account ref), `discountPercentage` (number), `website`, `bankAccountPresentation` ([CompanyBankAccountPresentation]), `isFactoring` (boolean — send invoices to factoring), `invoiceSendSMSNotification` (boolean), `invoiceSMSNotificationNumber` (string — Norwegian phone number), `isAutomaticSoftReminderEnabled` (boolean), `isAutomaticReminderEnabled` (boolean), `isAutomaticNoticeOfDebtCollectionEnabled` (boolean).

## Call-saving Patterns

- **POST returns full object** with `id`, `version`, all fields, and nested object IDs (including `postalAddress.id` even for name-only creation). Cache everything — no GET needed.
- **Address updates don't need old address IDs**: on PUT, include `postalAddress` without `id`/`version` — Tripletex creates a new address object replacing the old one. No need to GET or track address IDs.
- If creating a customer just to use in an invoice, pass the returned `id` directly into the invoice — don't re-query.

## Minimum Payload
```json
POST /customer
{"name": "X"}
```

With address:
```json
POST /customer
{"name": "X", "postalAddress": {"addressLine1": "...", "postalCode": "...", "city": "..."}, "isPrivateIndividual": true}
```

## Update — PUT /customer/{id}

Requires `id` and `version` in body.
```json
PUT /customer/{id}
{"id": X, "version": V, "name": "New Name"}
```

### Updating nested addresses
<!-- Corrected: address without id/version is NOT silently ignored — it creates a new address object. Verified 2026-03-20. -->
Including `postalAddress` in a PUT **without** `id`/`version` creates a **new address object** (replacing the old one). This works and is the simplest approach:
```json
PUT /customer/{id}
{
  "id": CUST_ID, "version": CUST_V,
  "postalAddress": {"addressLine1": "Storgata 45", "postalCode": "0182", "city": "Oslo"}
}
```
Do NOT try to reuse an old address `id` — Tripletex rejects reusing address IDs from previous objects with: "Eksisterende adresser kan ikke gjenbrukes på andre objekter."

## Delete
`DELETE /customer/{id}` → 204 (succeeds if no invoice references the customer).

## API Reference

### GET /customer
Query params: `id`, `customerAccountNumber`, `organizationNumber`, `email`, `invoiceEmail`, `customerName`, `phoneNumberMobile`, `isInactive`, `accountManagerId`, `changedSince`

### POST /customer
Create customer. Related addresses may also be created.

### GET /customer/{id}
### PUT /customer/{id}
### DELETE /customer/{id}

### GET /customer/category
Query params: `id`, `name`, `number`, `description`, `type`

### POST /customer/category
CustomerCategory writable fields: `name`, `number`, `description`, `type`, `displayName`

### GET /customer/category/{id}
### PUT /customer/category/{id}

### POST /customer/list
[BETA] Create multiple customers.

### PUT /customer/list
[BETA] Update multiple customers.
