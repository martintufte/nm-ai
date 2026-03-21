# Task 1: Tripletex - AI Accounting Agent

## Overview
Build an AI agent that receives accounting task prompts and executes them via the Tripletex API.
You must provide an HTTPS endpoint URL. The system sends POST requests to your `/solve` endpoint.

## Request Format (sent to your endpoint)
```json
{
  "prompt": "Accounting task in one of 7 languages",
  "tripletex_credentials": {
    "base_url": "Tripletex API proxy URL",
    "session_token": "Auth credential for Tripletex API"
  },
  "files": ["Optional base64-encoded PDFs/images"]
}
```

## Response
Must return `{"status": "completed"}` with HTTP 200 within **300 seconds**.

## Authentication to Tripletex
Basic Auth with username = `"0"`, password = `session_token`.

## Task Categories
- Employees (create, roles, contact info)
- Customers & products
- Invoicing, payments, credit notes
- Travel expense reports
- Project management
- Departments
- Corrections/deletions

## Task Tiers (unlock over time)
| Tier | Unlocks | Multiplier | Description |
|------|---------|------------|-------------|
| 1 | Start (Thursday) | 1x | Foundational operations |
| 2 | Friday | 2x | Multi-step workflows |
| 3 | Saturday | 3x | Complex scenarios |

## Scoring
- **30 unique tasks**, each with 56 variants (7 languages x 8 datasets)
- Field-by-field correctness: `points_earned / max_points`
- Multiplied by tier weight (1x, 2x, 3x)
- **Efficiency bonus** (up to 2x) for perfect submissions: fewer API calls + fewer 4xx errors
- Benchmarks recalculated every 12 hours

## Sandbox
Free test environment: `https://kkpqfuj-amager.tripletex.dev` (tokens expire March 31)

## Tips
- Use `?fields=` parameter for selective fetches
- Avoid trial-and-error (4xx errors hurt efficiency score)
- Batch operations when possible
