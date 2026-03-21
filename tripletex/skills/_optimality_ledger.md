# Optimality — Ledger

## Payroll voucher: 2 calls (not 4)

You need a salary expense account (5000-series) and a salary payable account (2920-series). Fetch both in one call.

Bad (4 calls):
```
GET /ledger/account?number=5000&count=5   → salary expense
GET /ledger/account?number=2920&count=5   → salary payable
GET /salary/payslip?count=1               → exploring if salary API exists
POST /ledger/voucher                      → create voucher
```

Good (2 calls):
```
GET /ledger/account?number=5000,2920&count=5  → returns both accounts in one call
POST /ledger/voucher                           → create voucher
```

The `number` param accepts comma-separated values. Don't use `count=50` without filtering — it returns too many accounts and gets truncated.

## Don't explore the salary API

If the task says to use manual vouchers, go straight to `POST /ledger/voucher`. Don't waste a call checking `GET /salary/payslip` first.
