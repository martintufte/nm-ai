## Sandbox Usage

The sandbox is the grounding for all investigation. Access is flexible — use whatever fits the task.

### Environment

Assume `TRIPLETEX_SANDBOX_API_URL` and `TRIPLETEX_SANDBOX_TOKEN` are already set.

The Python CLI uses different var names, so prefix commands with the mapping:
```bash
TRIPLETEX_BASE_URL="${TRIPLETEX_SANDBOX_API_URL}" TRIPLETEX_SESSION_TOKEN="${TRIPLETEX_SANDBOX_TOKEN}" uv run python tripletex/scripts/tripletex_cli.py ...
```

### Python CLI (`tripletex_cli.py`)

```bash
TRIPLETEX_BASE_URL="${TRIPLETEX_SANDBOX_API_URL}" TRIPLETEX_SESSION_TOKEN="${TRIPLETEX_SANDBOX_TOKEN}" \
  uv run python tripletex/scripts/tripletex_cli.py get customer --params '{"customerName": "Acme"}'

TRIPLETEX_BASE_URL="${TRIPLETEX_SANDBOX_API_URL}" TRIPLETEX_SESSION_TOKEN="${TRIPLETEX_SANDBOX_TOKEN}" \
  uv run python tripletex/scripts/tripletex_cli.py post department --data '{"name": "Test Dept"}'

TRIPLETEX_BASE_URL="${TRIPLETEX_SANDBOX_API_URL}" TRIPLETEX_SESSION_TOKEN="${TRIPLETEX_SANDBOX_TOKEN}" \
  uv run python tripletex/scripts/tripletex_cli.py review-plan "1. GET /department\n2. POST /employee"
```

### curl

Always write to a file and check the HTTP status code. If the code is 000, the sandbox is unreachable — retry after a short wait.

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" -u "0:$TRIPLETEX_SANDBOX_TOKEN" \
  "$TRIPLETEX_SANDBOX_API_URL/customer?customerName=Acme" \
  -o /tmp/tt.json && python3 -m json.tool /tmp/tt.json

curl -s -w "\nHTTP_CODE:%{http_code}\n" -u "0:$TRIPLETEX_SANDBOX_TOKEN" \
  -X POST -H "Content-Type: application/json" \
  -d '{"name": "Test Dept"}' \
  "$TRIPLETEX_SANDBOX_API_URL/department" \
  -o /tmp/tt.json && python3 -m json.tool /tmp/tt.json
```

### Tips

- Use `?fields=*` to see all available fields on an entity.

### Inline scripts

Write throwaway Python/bash inline for multi-step sequences, conditional logic, parsing responses. No need for a formal script.
