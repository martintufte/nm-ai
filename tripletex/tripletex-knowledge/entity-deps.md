# Entity Dependencies: What Must Exist Before Creating X

## No dependencies (can create from scratch)
- **Customer** — just `name`
- **Department** — just `name`
- **Product** — just `name`

## Requires existing entities
- **Employee** → Department (required), email (for STANDARD/EXTENDED userType)
- **Employment** → Employee (required). NOT auto-created with employee. Holds `startDate`.
- **Project** → Employee (as `projectManager`), startDate
- **Order** → Customer
- **Order line** → Order + Product
- **Invoice** → Customer + Orders with OrderLines (inline) + Company bank account number set
- **Invoice payment** → Invoice (uses query params, needs PaymentType ID from lookup)
- **Credit note** → Invoice (uses query params)
- **Travel expense** → Employee
- **Travel expense cost** → TravelExpense + CostCategory ID + TravelPaymentType ID + Currency ID
- **Travel expense mileage** → TravelExpense + RateCategory ID (type=MILEAGE_ALLOWANCE, must be date-valid)
- **Travel expense per diem** → TravelExpense + RateCategory ID (type=PER_DIEM, must be date-valid) + location string
- **Accommodation allowance** → TravelExpense + RateCategory ID (type=ACCOMMODATION_ALLOWANCE, date-valid) + location string
- **Mileage passenger supplement** → TravelExpense + RateCategory ID 744 (separate entry from main mileage)

## One-time setup (per company)
- **Bank account number** must be set on a bank ledger account before any invoice can be created
  - `PUT /ledger/account/{id}` with `bankAccountNumber` field
  - Find bank accounts: `GET /ledger/account?isBankAccount=true`

## Creation order for full invoice workflow
1. Customer (if not exists) — 1 call
2. Product (if not exists) — 1 call
3. Bank account number (if not set) — 1 PUT call
4. `POST /invoice` with inline orders+orderLines — 1 call (creates Order, OrderLines, Invoice together)
5. `PUT /invoice/{id}/:payment?...` — 1 call (query params)
6. `PUT /invoice/{id}/:createCreditNote?...` — 1 call if needed

**Minimum total: 2-4 calls** (customer + product + invoice + payment)

## Creation order for travel expense workflow
1. Employee must exist
2. `POST /travelExpense` with employee ref and `travelDetails` — 1 call
3. Add costs: `POST /travelExpense/cost` per cost item
4. Add mileage: `POST /travelExpense/mileageAllowance` per leg
5. Add per diem: `POST /travelExpense/perDiemCompensation`
6. Add accommodation: `POST /travelExpense/accommodationAllowance`

**Rate category lookup:** Current categories are at offset ~400+ in the paginated list. Use `GET /travelExpense/rateCategory?from=400&count=60` to find 2026-valid categories.
