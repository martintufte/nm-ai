"""Build a compact API reference from the Tripletex OpenAPI spec.

Uses the full OpenAPI spec (tripletex-openapi.json) as the source of truth,
filtered to competition-relevant endpoints via the competition spec's path list.
Outputs tripletex/api_reference.md with one section per endpoint:
HTTP method + path, summary, and writable fields with types.

Includes empirically-discovered annotations for fields/behaviors
that the OpenAPI spec gets wrong or omits.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Empirical annotations not captured in the OpenAPI spec ──────────────
# These were discovered by testing the live API and are critical for correct usage.

# Fields the spec doesn't mark as required but the API actually requires
SECRETLY_REQUIRED_FIELDS: dict[str, dict[str, str]] = {
    "Employee": {
        "userType": '**secretly required.** Values: "STANDARD", "EXTENDED", "NO_ACCESS"',
        "department": "**secretly required.** Must be `{\"id\": DEPT_ID}`",
        "email": "**required for STANDARD/EXTENDED userType** (not NO_ACCESS)",
        "dateOfBirth": "**required on PUT** (not on POST)",
    },
    "Project": {
        "startDate": "**secretly required.** ISO date string",
    },
    "PerDiemCompensation": {
        "location": "**secretly required.**",
    },
}

# Notes to append after specific endpoint headers (method + path -> list of note lines)
ENDPOINT_NOTES: dict[str, list[str]] = {
    "POST /employee": [
        "**Note:** `userType` and `department` are required despite not being marked so in the spec.",
        "Minimum NO_ACCESS: `{\"firstName\":\"X\",\"lastName\":\"Y\",\"userType\":\"NO_ACCESS\",\"department\":{\"id\":DEPT_ID}}`",
        "Minimum STANDARD: add `\"email\":\"x@y.com\"` to the above.",
        "Employment is NOT auto-created; use `\"employments\":[{\"startDate\":\"YYYY-MM-DD\"}]` to inline it.",
    ],
    "POST /invoice": [
        "**PREREQUISITE:** Company must have a bank account number set (`PUT /ledger/account/{id}` with `bankAccountNumber`).",
        "`orders` must be non-empty (at least one order with orderLines). Each inline order needs `deliveryDate`.",
    ],
    "PUT /invoice/{id}/:payment": [
        "**Uses QUERY PARAMS, not request body!** `?paymentDate=YYYY-MM-DD&paymentTypeId=X&paidAmount=1000.0`",
        "All three query params are required. Send empty body.",
    ],
    "PUT /invoice/{id}/:createCreditNote": [
        "**Uses QUERY PARAMS, not request body!** `?date=YYYY-MM-DD&comment=reason`",
        "`date` required, `comment` optional. Returns a new invoice object (the credit note).",
    ],
    "POST /travelExpense": [
        "**Note:** Dates (`departureDate`, `returnDate`) go inside nested `travelDetails`, NOT at top level.",
        "Minimum: `{\"employee\":{\"id\":X},\"travelDetails\":{\"departureDate\":\"...\",\"returnDate\":\"...\",\"isDayTrip\":true}}`",
    ],
    "POST /travelExpense/cost": [
        "**Note:** Use `amountCurrencyIncVat` for the amount, NOT `amount` (that field doesn't exist on POST).",
    ],
    "POST /travelExpense/perDiemCompensation": [
        "**Note:** `location` is secretly required. `count` is number of days (integer), NOT a date range.",
        "`overnightAccommodation`: e.g. `\"HOTEL\"`, `\"NONE\"`.",
    ],
    "POST /travelExpense/mileageAllowance": [
        "**Note:** Passenger supplement is a SEPARATE mileage entry using rate category 744, not a boolean field.",
    ],
    "POST /travelExpense/accommodationAllowance": [
        "**Note:** `location` is secretly required.",
    ],
    "POST /product": [
        "**Note:** Product names must be unique. Omit `vatType` — most VAT codes are invalid for products.",
        "`priceIncludingVatCurrency` does NOT auto-calculate excl price; always set `priceExcludingVatCurrency` explicitly.",
    ],
    "POST /project": [
        "**Note:** `startDate`, `projectManager`, and `isInternal` are all required despite the spec not marking them.",
    ],
    "POST /order": [
        "**Note:** When used inside an invoice, `deliveryDate` is secretly required on each order.",
    ],
    "PUT /customer/{id}": [
        "**Note:** Nested objects (e.g. `postalAddress`) require their own `id`/`version` or updates are silently ignored.",
    ],
    "PUT /employee/{id}": [
        "**Note:** `dateOfBirth` is required on PUT (not required on POST).",
    ],
    "DELETE /invoice/{id}": [
        "**Returns 403 Forbidden.** Invoices cannot be deleted; use `PUT /invoice/{id}/:createCreditNote` to void.",
    ],
    "DELETE /order/{id}": [
        "**Returns 422 if invoices exist.** Orders with invoices are permanent.",
    ],
}


def schema_type_str(prop: dict) -> str:
    """Return a concise type string for a schema property."""
    if "$ref" in prop:
        return prop["$ref"].rsplit("/", 1)[-1]
    t = prop.get("type", "object")
    if t == "array":
        items = prop.get("items", {})
        inner = schema_type_str(items)
        return f"[{inner}]"
    fmt = prop.get("format")
    if fmt:
        return f"{t}({fmt})"
    return t


def resolve_schema(ref_or_inline: dict, schemas: dict) -> dict | None:
    """Resolve a $ref to its schema, or return inline schema."""
    if "$ref" in ref_or_inline:
        name = ref_or_inline["$ref"].rsplit("/", 1)[-1]
        return schemas.get(name)
    return ref_or_inline


def writable_fields(schema: dict, schemas: dict, schema_name: str = "") -> list[str]:
    """Return lines describing writable fields of a schema."""
    lines = []
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    secret_reqs = SECRETLY_REQUIRED_FIELDS.get(schema_name, {})

    for name, prop in props.items():
        if prop.get("readOnly"):
            continue
        # Skip meta fields that aren't useful for creation
        if name in ("id", "version", "changes", "url"):
            continue

        typ = schema_type_str(prop)
        req = " **required**" if name in required else ""
        # Add empirical annotations for secretly required fields
        secret = secret_reqs.get(name)
        if secret:
            req = f" — {secret}" if not req else f" **required** — {secret}"
        desc = prop.get("description", "")
        # Truncate long descriptions
        if len(desc) > 80:
            desc = desc[:77] + "..."
        suffix = f" — {desc}" if (desc and not secret) else ""
        lines.append(f"  - `{name}`: {typ}{req}{suffix}")

    return lines


def get_request_body_schema(operation: dict) -> str | None:
    """Extract the $ref schema name from a request body."""
    rb = operation.get("requestBody", {})
    content = rb.get("content", {})
    for media in content.values():
        schema = media.get("schema", {})
        if "$ref" in schema:
            return schema["$ref"].rsplit("/", 1)[-1]
    return None


def build_reference(spec: dict) -> str:
    """Build the markdown API reference."""
    schemas = spec.get("components", {}).get("schemas", {})
    paths = spec.get("paths", {})

    lines = ["# Tripletex API Reference (Competition Subset)", ""]

    # Group paths by resource prefix
    groups: dict[str, list[tuple[str, str, dict]]] = {}
    for path, ops in sorted(paths.items()):
        # Extract resource group from path
        parts = path.strip("/").split("/")
        group = parts[0] if parts else "other"
        # Handle compound prefixes like ledger/account
        if len(parts) > 1 and parts[0] == "ledger":
            group = f"ledger/{parts[1]}"

        for method, operation in sorted(ops.items()):
            if method in ("parameters", "servers"):
                continue
            groups.setdefault(group, []).append((path, method.upper(), operation))

    # Track which schemas we've already printed fields for
    printed_schemas: set[str] = set()

    for group, endpoints in sorted(groups.items()):
        lines.append(f"## {group}")
        lines.append("")

        for path, method, operation in endpoints:
            summary = operation.get("summary", "")
            endpoint_key = f"{method} {path}"
            lines.append(f"### `{endpoint_key}`")
            if summary:
                lines.append(summary)
            lines.append("")

            # Inject empirical endpoint notes
            notes = ENDPOINT_NOTES.get(endpoint_key, [])
            if notes:
                for note in notes:
                    lines.append(note)
                lines.append("")

            # Query parameters
            params = operation.get("parameters", [])
            query_params = [p for p in params if p.get("in") == "query"]
            if query_params:
                # For GET: show important params; for others: show required params
                if method == "GET":
                    show_params = [
                        p
                        for p in query_params
                        if p["name"] not in ("from", "count", "sorting", "fields")
                    ]
                else:
                    # For non-GET, only show required query params (PUT actions)
                    show_params = [p for p in query_params if p.get("required")]

                if show_params:
                    parts_list = []
                    for p in show_params[:10]:
                        name_str = f"`{p['name']}`"
                        if p.get("required"):
                            name_str += " **(required)**"
                        parts_list.append(name_str)
                    names = ", ".join(parts_list)
                    if len(show_params) > 10:
                        names += f" (+{len(show_params) - 10} more)"
                    lines.append(f"Query params: {names}")
                    lines.append("")

            # Request body schema fields
            schema_name = get_request_body_schema(operation)
            if schema_name and schema_name not in printed_schemas:
                schema = schemas.get(schema_name)
                if schema:
                    printed_schemas.add(schema_name)
                    fields = writable_fields(schema, schemas, schema_name)
                    if fields:
                        lines.append(f"**{schema_name}** writable fields:")
                        lines.extend(fields)
                        lines.append("")
            elif schema_name and schema_name in printed_schemas:
                lines.append(f"Body: `{schema_name}` (see above)")
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    full_spec_path = root / "docs" / "tripletex-openapi.json"
    comp_spec_path = root / "docs" / "tripletex-openapi-competition.json"
    output_path = root / "api_reference.md"

    with full_spec_path.open() as f:
        full_spec = json.load(f)

    with comp_spec_path.open() as f:
        comp_spec = json.load(f)

    # Use full spec schemas but only competition-relevant paths
    comp_paths = set(comp_spec.get("paths", {}).keys())
    filtered_paths = {
        path: ops
        for path, ops in full_spec.get("paths", {}).items()
        if path in comp_paths
    }

    spec = {
        "paths": filtered_paths,
        "components": full_spec.get("components", {}),
    }

    reference = build_reference(spec)

    with output_path.open("w") as f:
        f.write(reference)

    # Stats
    size_kb = output_path.stat().st_size / 1024
    # Rough token estimate: ~4 chars per token
    est_tokens = len(reference) / 4
    logger.info("Output: %s", output_path)
    logger.info("Size: %.1f KB (~%.0f tokens)", size_kb, est_tokens)


if __name__ == "__main__":
    main()
