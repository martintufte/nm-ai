# Optimality — Minimizing API Calls

Every Tripletex API call counts toward your score. Review your plan against these techniques before executing.

## Technique 1: List GETs return full objects

`GET /customer?customerName=X` returns `values[]` where each item has `id`, `version`, and all nested fields (addresses, contacts, etc.). **Never re-GET by ID after a list search.**

Bad (2 calls):
```
GET /customer?customerName=Acme      → values[0].id = 123
GET /customer/123                    → same data you already had
```

Good (1 call):
```
GET /customer?customerName=Acme      → values[0].id = 123, use directly
```

## Technique 2: Reuse POST response IDs

POST returns the full created object with `id` and `version`. Use them directly for subsequent calls.

Bad (3 calls):
```
POST /customer {"name":"Acme"}       → id=123
GET /customer/123                    → unnecessary, you already have the id
POST /invoice {..., "customer":{"id":123}}
```

Good (2 calls):
```
POST /customer {"name":"Acme"}       → id=123
POST /invoice {..., "customer":{"id":123}}
```

## Technique 3: Inline creation

Nest child objects in the parent POST. One call instead of many. See the domain-specific optimality skills below for complete inline capabilities per endpoint.

## Technique 4: Don't GET before POST for new entities

If the task says "create customer X", POST directly. It doesn't exist yet.

## Technique 5: Combine lookups into fewer GETs

If you need multiple entities from the same endpoint, use one call with comma-separated IDs/numbers instead of separate calls.

Bad (2 calls):
```
GET /ledger/account?number=5000&count=5   → salary expense account
GET /ledger/account?number=2920&count=5   → salary payable account
```

Good (1 call):
```
GET /ledger/account?number=5000,2920&count=5  → both accounts in one call
```

Many list params accept comma-separated values.

## Technique 6: Don't make speculative API calls

Only call endpoints the task requires. Don't explore whether alternative APIs exist — use the approach the task describes or that you already know works.

## Domain-specific optimality skills

Each domain has its own optimality patterns with inline capabilities and common pitfalls:

- `_optimality_employee` — inline employment + details (3→1), department lookup
- `_optimality_invoice` — inline orders + orderlines (3→1), payment/credit via query params, bank account
- `_optimality_travel` — inline ALL 4 sub-resources (5→1), passenger supplement, rate categories
- `_optimality_project` — inline participants + activities (3→1), project manager entitlement
- `_optimality_ledger` — ledger account lookups, payroll vouchers (4→2)
