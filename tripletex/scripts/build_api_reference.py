"""Build a compact API reference from the competition OpenAPI spec.

Outputs tripletex/api_reference.md with one section per endpoint:
HTTP method + path, summary, and writable fields with types.
Target size: ~10-15K tokens for inclusion in the system prompt.
"""

import json
from pathlib import Path


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


def writable_fields(schema: dict, schemas: dict) -> list[str]:
    """Return lines describing writable fields of a schema."""
    lines = []
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    for name, prop in props.items():
        if prop.get("readOnly"):
            continue
        # Skip meta fields that aren't useful for creation
        if name in ("id", "version", "changes", "url"):
            continue

        typ = schema_type_str(prop)
        req = " **required**" if name in required else ""
        desc = prop.get("description", "")
        # Truncate long descriptions
        if len(desc) > 80:
            desc = desc[:77] + "..."
        suffix = f" — {desc}" if desc else ""
        lines.append(f"  - `{name}`: {typ}{req}{suffix}")

    return lines


def get_request_body_schema(operation: dict) -> str | None:
    """Extract the $ref schema name from a request body."""
    rb = operation.get("requestBody", {})
    content = rb.get("content", {})
    for ct, media in content.items():
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
            lines.append(f"### `{method} {path}`")
            if summary:
                lines.append(summary)
            lines.append("")

            # Query parameters (for GET)
            params = operation.get("parameters", [])
            query_params = [p for p in params if p.get("in") == "query"]
            if query_params and method == "GET":
                important_params = [
                    p for p in query_params
                    if p["name"] not in ("from", "count", "sorting", "fields")
                ]
                if important_params:
                    names = ", ".join(f"`{p['name']}`" for p in important_params[:10])
                    if len(important_params) > 10:
                        names += f" (+{len(important_params) - 10} more)"
                    lines.append(f"Query params: {names}")
                    lines.append("")

            # Request body schema fields
            schema_name = get_request_body_schema(operation)
            if schema_name and schema_name not in printed_schemas:
                schema = schemas.get(schema_name)
                if schema:
                    printed_schemas.add(schema_name)
                    fields = writable_fields(schema, schemas)
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
    input_path = root / "docs" / "tripletex-openapi-competition.json"
    output_path = root / "api_reference.md"

    with open(input_path) as f:
        spec = json.load(f)

    reference = build_reference(spec)

    with open(output_path, "w") as f:
        f.write(reference)

    # Stats
    size_kb = output_path.stat().st_size / 1024
    # Rough token estimate: ~4 chars per token
    est_tokens = len(reference) / 4
    print(f"Output: {output_path}")
    print(f"Size: {size_kb:.1f} KB (~{est_tokens:.0f} tokens)")


if __name__ == "__main__":
    main()
