# Optimality — Ledger

## Use GET /ledger for account totals, not GET /ledger/posting

When the task needs per-account totals (e.g. "which expense accounts had the largest increase"), use `GET /ledger` — it returns aggregated `sumAmount` and `closingBalance` per account. Do NOT fetch all postings and compute totals manually.

Bad (3+ calls, huge response):
```
GET /ledger/posting?dateFrom=2026-01-01&dateTo=2026-02-01&count=1000  → raw postings dump
GET /ledger/posting?dateFrom=2026-02-01&dateTo=2026-03-01&count=1000  → raw postings dump
# Then manually sum per account in agent reasoning
```

Good (2 calls, compact):
```
GET /ledger?dateFrom=2026-01-01&dateTo=2026-02-01&fields=account(number,name),sumAmount
GET /ledger?dateFrom=2026-02-01&dateTo=2026-03-01&fields=account(number,name),sumAmount
```

The `fields` filter keeps the response small. Each result row has the account and its total — no post-processing needed.

## Payroll voucher: 3 calls (not 5)

You need the employee ID (for the posting `employee` ref), a salary expense account (5000-series), and a salary payable account (2920-series). Fetch both accounts in one call.

Bad (5 calls):
```
GET /employee?firstName=...               → find employee
GET /ledger/account?number=5000&count=5   → salary expense
GET /ledger/account?number=2920&count=5   → salary payable
GET /salary/payslip?count=1               → exploring if salary API exists
POST /ledger/voucher                      → create voucher
```

Good (3 calls):
```
GET /employee?firstName=...&count=1            → get employee ID
GET /ledger/account?number=5000,2920&count=5   → returns both accounts in one call
POST /ledger/voucher                            → create voucher with employee ref on postings
```

Include `"employee": {"id": EMPLOYEE_ID}` on each posting so the payroll entry is linked to the correct employee. The `number` param accepts comma-separated values. Don't use `count=50` without filtering — it returns too many accounts and gets truncated.

## Combine same-date journal entries into one voucher (N calls → 1)

Multiple journal entries on the same date belong in one voucher with all posting pairs.

Bad (3 calls):
```
POST /ledger/voucher {"date":"2026-03-31", "postings":[{debit 7700},{credit 1710}]}
POST /ledger/voucher {"date":"2026-03-31", "postings":[{debit 6010},{credit 1710}]}
POST /ledger/voucher {"date":"2026-03-31", "postings":[{debit 5000},{credit 2900}]}
```

Good (1 call):
```
POST /ledger/voucher {"date":"2026-03-31", "postings":[
  {debit 7700, row:1},{credit 1710, row:2},
  {debit 6010, row:3},{credit 1710, row:4},
  {debit 5000, row:5},{credit 2900, row:6}
]}
```

## Receipt voucher: 3 calls (not 6)

Booking a receipt needs the department ID, the expense + bank account IDs, and the voucher POST. Batch the account lookup.

Bad (6 calls):
```
GET /department?count=20                              → scan all departments
GET /department?from=20&count=5                       → paginate
GET /department?name=Markedsføring                    → finally filter by name
GET /ledger/account?number=6540&count=5               → expense account
GET /ledger/account?isBankAccount=true&count=10       → bank account
POST /ledger/voucher                                  → create voucher
```

Good (3 calls):
```
GET /department?name=Markedsføring&count=5            → direct name lookup
GET /ledger/account?number=6540,1920&count=5          → both accounts in one call
POST /ledger/voucher                                  → create voucher
```

When you know the account numbers, use `number=X,Y` — don't search by `isBankAccount` separately. Use 1920 (Bankinnskudd) as the default bank/card payment account unless the task specifies otherwise.

## Don't explore the salary API

If the task says to use manual vouchers, go straight to `POST /ledger/voucher`. Don't waste a call checking `GET /salary/payslip` first.
