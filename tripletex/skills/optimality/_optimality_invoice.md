# Optimality — Invoice

## Inline orders + orderlines: 1 POST (not 3)

Invoice, orders, and order lines can all be created in a single `POST /invoice`.

Bad (3 calls):
```
POST /order {"orderDate":"...","customer":{"id":C}}         → id=O
POST /order/orderline {"order":{"id":O},"product":{"id":P}} → id=L
POST /invoice {"orders":[{"id":O}]}
```

Good (1 call):
```
POST /invoice {
  "invoiceDate":"...", "invoiceDueDate":"...",
  "customer": {"id": C},
  "orders": [{
    "orderDate":"...", "deliveryDate":"...",
    "customer": {"id": C},
    "orderLines": [{"product": {"id": P}, "count": 2}]
  }]
}
```

Multiple order lines go in the same `orderLines` array. Multiple orders (rare) go in the `orders` array.

## Payment + credit note: use params dict (not body)

Both use PUT with `params` dict. Sending JSON body → 422.

```
PUT /invoice/{id}/:payment
params: {"paymentDate": "YYYY-MM-DD", "paymentTypeId": X, "paidAmount": 1000}
data: {}

PUT /invoice/{id}/:createCreditNote
params: {"date": "YYYY-MM-DD", "comment": "reason"}
data: {}
```

## Payment type lookup: 1 call (unavoidable)

`GET /invoice/paymentType` returns the payment type IDs needed for `:payment`. This is unavoidable when registering payment.

## Bank account: don't check proactively

Bank account setup (`GET /ledger/account?isBankAccount=true` → `PUT`) is only needed if invoice creation fails with "Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer." Don't spend calls checking in advance — retry only if you get that error.

## Don't GET customer/product before POST for new entities

If the task says "create customer X and product Y, then invoice", POST them directly and use the returned IDs. Don't GET to check if they exist.

## VAT type IDs: don't look up

`GET /ledger/vatType` is unnecessary for invoicing. Common VAT IDs are documented in the product skill:
- id=3 → 25 % (standard)
- id=31 → 15 % (food/næringsmiddel)
- id=6 → 0 % (exempt)

Use directly as `"vatType": {"id": 3}` on order lines or products.

Bad (1 wasted call):
```
GET /ledger/vatType?count=50   ← unnecessary
POST /invoice ...
```

Good (0 lookups):
```
POST /invoice {
  "orders": [{"orderLines": [
    {"product": {"id": P}, "vatType": {"id": 3}, "count": 1}
  ]}]
}
```

## Product lookup by productNumber: batch when possible

`GET /product` accepts `productNumber` as an array parameter. When looking up multiple products by number, batch into one call.

Bad (3 calls):
```
GET /product?productNumber=3296
GET /product?productNumber=6620
GET /product?productNumber=8441
```

Good (1 call):
```
GET /product?productNumber=3296&productNumber=6620&productNumber=8441
```

Returns all 3 products in a single response. Use the returned IDs directly in order lines.
