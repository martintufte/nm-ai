# Product

## Dependencies
None — product can be created from scratch.

## Required Fields — POST /product

| Field | Required? | Notes |
|-------|-----------|-------|
| `name` | Yes | Must be **unique** across all products. Error if duplicate: "Produktnavnet X er allerede registrert." |

Optional fields: `number`, `description`, `orderLineDescription`, `ean`, `costExcludingVatCurrency` (number — purchase cost excl VAT), `expenses` (number), `priceExcludingVatCurrency` (number), `priceIncludingVatCurrency` (number), `isInactive`, `productUnit` (ProductUnit ref), `isStockItem`, `currency` (Currency ref), `department` (Department ref), `account` (Account ref), `supplier` (Supplier ref), `resaleProduct` (Product ref), `discountGroup` (DiscountGroup ref), `weight` (number), `weightUnit` (string), `volume` (number), `volumeUnit` (string), `hsnCode` (string), `image` (Document), `mainSupplierProduct` (SupplierProduct ref), `minStockLevel` (number — minimum stock level, stock items only), `hasSupplierProductConnected` (boolean).

## Gotchas

- **vatType** requires the company to be VAT-registered. When registered, common outgoing codes: id=3 (25%), id=31 (15%), id=32 (12%); ingoing: id=1 (25%); zero-rate: id=6 (0%). "Ugyldig mva-kode" means the company isn't VAT-registered (only id=0 and id=6 work without registration).
- **`priceIncludingVatCurrency` does NOT auto-calculate excl price.** Setting it stores both incl and excl as the same value. Always set `priceExcludingVatCurrency` explicitly.

## Call-saving Patterns

- **POST returns full object** with `id`, `version`. Reuse directly in order lines / invoices.
- If creating a product just for an invoice, pass the returned `id` into the order line — no need to look it up.

## Minimum Payload
```json
POST /product
{"name": "X"}
```

With price:
```json
POST /product
{"name": "X", "priceExcludingVatCurrency": 500.0}
```

With unit:
```json
POST /product
{"name": "X", "priceExcludingVatCurrency": 500.0, "productUnit": {"id": UNIT_ID}}
```

## Update — PUT /product/{id}
Requires `id` and `version`.
```json
PUT /product/{id}
{"id": X, "version": V, "name": "X", "priceExcludingVatCurrency": 999.0}
```

## Delete
`DELETE /product/{id}` → 204 (succeeds if no order line references the product).

## API Reference

### GET /product
Query params: `number`, `ids`, `productNumber`, `name`, `ean`, `isInactive`, `isStockItem`, `isSupplierProduct`, `supplierId`, `currencyId` (+10 more)

### POST /product
Create new product. Returns full object.

### GET /product/{id}
### PUT /product/{id}
### DELETE /product/{id}

### GET /product/unit
Query params: `id`, `name`, `nameShort`, `commonCode`

### POST /product/unit
ProductUnit writable fields: `name`, `nameEN`, `nameShort`, `nameShortEN`, `commonCode`

### GET /product/unit/{id}
### PUT /product/unit/{id}
### DELETE /product/unit/{id}
### GET /product/unit/query
Wildcard search. Query params: `query`
### GET /product/unit/master
Query params: `id`, `name`, `nameShort`, `commonCode`, `peppolName`, `peppolSymbol`, `isInactive`

### GET /product/discountGroup
Query params: `id`, `name`, `number`
### GET /product/discountGroup/{id}

### POST /product/list
Add multiple products.
### PUT /product/list
Update multiple products.

### POST /product/{id}/image
Upload image (replaces existing).
### DELETE /product/{id}/image

### GET /product/external
[BETA] Find external products. Query params: `name`, `wholesaler`, `isInactive`, `productGroupId`
### GET /product/external/{id}

### GET /product/productPrice
Find prices. Query params: `productId` **(required)**

## Supplier Products

### POST /product/supplierProduct
SupplierProduct writable fields: `name`, `number`, `description`, `ean`, `costExcludingVatCurrency`, `cost`, `priceExcludingVatCurrency`, `priceIncludingVatCurrency`, `isInactive`, `productUnit` (ref), `isStockItem`, `vatType` (ref), `currency` (ref), `supplier` (ref), `resaleProduct` (Product ref), `isMainSupplierProduct` (boolean — pilot feature).

### GET /product/supplierProduct
Query params: `productId`, `vendorId`, `query`, `isInactive`
### POST /product/supplierProduct/list
### PUT /product/supplierProduct/list
### GET /product/supplierProduct/{id}
### PUT /product/supplierProduct/{id}
### DELETE /product/supplierProduct/{id}

## Product Groups

### POST /product/group
ProductGroup writable fields: `name`, `parentGroup` (ProductGroup ref).

### GET /product/group
Query params: `id`, `name`, `isInactive`
### GET /product/group/query
Wildcard search. Query params: `query`
### POST /product/group/list
### PUT /product/group/list
### DELETE /product/group/list — query params: `ids` **(required)**
### GET /product/group/{id}
### PUT /product/group/{id}
### DELETE /product/group/{id}

### POST /product/groupRelation
ProductGroupRelation writable fields: `product` (Product ref), `productGroup` (ProductGroup ref).

### GET /product/groupRelation
Query params: `id`, `productGroupId`, `productId`
### POST /product/groupRelation/list
### DELETE /product/groupRelation/list
### GET /product/groupRelation/{id}
### DELETE /product/groupRelation/{id}

## Inventory Locations

### POST /product/inventoryLocation
InventoryLocation writable fields: `product` (ref), `inventory` (Inventory ref), `isMainLocation` (boolean).

### GET /product/inventoryLocation
Query params: `productId`, `inventoryId`, `isMainLocation`
### POST /product/inventoryLocation/list
### PUT /product/inventoryLocation/list
### GET /product/inventoryLocation/{id}
### PUT /product/inventoryLocation/{id}
### DELETE /product/inventoryLocation/{id}

### GET /product/logisticsSettings
### PUT /product/logisticsSettings
