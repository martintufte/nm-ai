"""Extract competition-relevant subset of Tripletex OpenAPI spec."""

import json
import re
import sys
from pathlib import Path

PREFIXES = [
    "/employee",
    "/customer",
    "/product",
    "/invoice",
    "/order",
    "/travelExpense",
    "/project",
    "/department",
    "/ledger/account",
    "/ledger/posting",
    "/ledger/voucher",
]

REF_PATTERN = re.compile(r'"\$ref"\s*:\s*"#/components/schemas/([^"]+)"')


def collect_refs(obj: object) -> set[str]:
    """Collect all $ref schema names from a JSON-serializable object."""
    refs = set()
    text = json.dumps(obj)
    for match in REF_PATTERN.finditer(text):
        refs.add(match.group(1))
    return refs


def resolve_transitive(all_schemas: dict, initial_refs: set[str]) -> dict:
    """Transitively resolve all schema dependencies."""
    resolved = {}
    queue = list(initial_refs)
    seen = set()

    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        if name not in all_schemas:
            print(f"  WARNING: referenced schema '{name}' not found", file=sys.stderr)
            continue
        schema = all_schemas[name]
        resolved[name] = schema
        for dep in collect_refs(schema):
            if dep not in seen:
                queue.append(dep)

    return resolved


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    input_path = root / "docs" / "tripletex-openapi.json"
    output_path = root / "docs" / "tripletex-openapi-competition.json"

    with open(input_path) as f:
        spec = json.load(f)

    # Filter paths
    filtered_paths = {}
    for path, ops in spec.get("paths", {}).items():
        if any(path.startswith(prefix) or path == prefix for prefix in PREFIXES):
            # Also check we don't accidentally match e.g. /employeeCategory
            # by verifying the char after prefix is / or { or end-of-string
            for prefix in PREFIXES:
                if path.startswith(prefix):
                    rest = path[len(prefix):]
                    if rest == "" or rest[0] in ("/", "{", ":"):
                        filtered_paths[path] = ops
                        break

    print(f"Paths: {len(filtered_paths)} (from {len(spec.get('paths', {}))})")

    # Collect all $ref from filtered paths
    all_schemas = spec.get("components", {}).get("schemas", {})
    path_refs = collect_refs(filtered_paths)
    print(f"Direct schema refs from paths: {len(path_refs)}")

    # Transitively resolve
    resolved_schemas = resolve_transitive(all_schemas, path_refs)
    print(f"Schemas after transitive resolution: {len(resolved_schemas)} (from {len(all_schemas)})")

    # Build output spec
    output = {
        "openapi": spec["openapi"],
        "info": spec["info"],
        "servers": spec.get("servers", []),
        "paths": dict(sorted(filtered_paths.items())),
        "components": {
            "schemas": dict(sorted(resolved_schemas.items())),
        },
    }

    # Preserve securitySchemes if present
    if "securitySchemes" in spec.get("components", {}):
        output["components"]["securitySchemes"] = spec["components"]["securitySchemes"]

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    size_kb = output_path.stat().st_size / 1024
    print(f"Output: {output_path} ({size_kb:.0f} KB)")

    # Verification: check all $refs resolve
    output_text = json.dumps(output)
    all_refs_in_output = set(REF_PATTERN.findall(output_text))
    missing = all_refs_in_output - set(resolved_schemas.keys())
    if missing:
        print(f"ERROR: {len(missing)} unresolved $ref(s): {missing}", file=sys.stderr)
        sys.exit(1)
    else:
        print("All $ref references resolve correctly.")

    # Spot-check
    spot_checks = ["/employee", "/invoice", "/travelExpense/{id}", "/ledger/voucher/{id}/:reverse"]
    for path in spot_checks:
        status = "FOUND" if path in filtered_paths else "MISSING"
        print(f"  Spot-check {path}: {status}")


if __name__ == "__main__":
    main()
