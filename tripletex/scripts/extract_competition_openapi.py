"""Extract competition-relevant subset of Tripletex OpenAPI spec."""

import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

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
            logger.warning("referenced schema '%s' not found", name)
            continue
        schema = all_schemas[name]
        resolved[name] = schema
        queue.extend(dep for dep in collect_refs(schema) if dep not in seen)

    return resolved


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    input_path = root / "docs" / "tripletex-openapi.json"
    output_path = root / "docs" / "tripletex-openapi-competition.json"

    with input_path.open() as f:
        spec = json.load(f)

    # Filter paths
    filtered_paths = {}
    for path, ops in spec.get("paths", {}).items():
        if any(path.startswith(prefix) or path == prefix for prefix in PREFIXES):
            # Also check we don't accidentally match e.g. /employeeCategory
            # by verifying the char after prefix is / or { or end-of-string
            for prefix in PREFIXES:
                if path.startswith(prefix):
                    rest = path[len(prefix) :]
                    if rest == "" or rest[0] in ("/", "{", ":"):
                        filtered_paths[path] = ops
                        break

    logger.info("Paths: %d (from %d)", len(filtered_paths), len(spec.get("paths", {})))

    # Collect all $ref from filtered paths
    all_schemas = spec.get("components", {}).get("schemas", {})
    path_refs = collect_refs(filtered_paths)
    logger.info("Direct schema refs from paths: %d", len(path_refs))

    # Transitively resolve
    resolved_schemas = resolve_transitive(all_schemas, path_refs)
    logger.info(
        "Schemas after transitive resolution: %d (from %d)",
        len(resolved_schemas),
        len(all_schemas),
    )

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

    with output_path.open("w") as f:
        json.dump(output, f, indent=2)

    size_kb = output_path.stat().st_size / 1024
    logger.info("Output: %s (%.0f KB)", output_path, size_kb)

    # Verification: check all $refs resolve
    output_text = json.dumps(output)
    all_refs_in_output = set(REF_PATTERN.findall(output_text))
    missing = all_refs_in_output - set(resolved_schemas.keys())
    if missing:
        logger.error("%d unresolved $ref(s): %s", len(missing), missing)
        sys.exit(1)
    else:
        logger.info("All $ref references resolve correctly.")

    # Spot-check
    spot_checks = ["/employee", "/invoice", "/travelExpense/{id}", "/ledger/voucher/{id}/:reverse"]
    for path in spot_checks:
        found = "FOUND" if path in filtered_paths else "MISSING"
        logger.info("Spot-check %s: %s", path, found)


if __name__ == "__main__":
    main()
