from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "spec" / "openapi.json"
PYTHON_OUTPUT = ROOT / "src" / "aix_client" / "generated.py"
TYPESCRIPT_OUTPUT = ROOT / "clients" / "typescript" / "src" / "generated.ts"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def operations() -> dict[str, tuple[str, str]]:
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    result = {}
    for path, path_item in sorted(document["paths"].items()):
        for method, operation in sorted(path_item.items()):
            if method not in HTTP_METHODS:
                continue
            result[operation["operationId"]] = (method.upper(), path)
    return dict(sorted(result.items()))


def python_source(items: dict[str, tuple[str, str]]) -> str:
    rows = "\n".join(
        f'    "{name}": ("{method}", "{path}"),'
        for name, (method, path) in items.items()
    )
    return (
        '"""Generated from spec/openapi.json. Do not edit manually."""\n\n'
        "OPERATIONS: dict[str, tuple[str, str]] = {\n"
        f"{rows}\n"
        "}\n"
    )


def typescript_source(items: dict[str, tuple[str, str]]) -> str:
    rows = "\n".join(
        f"  {json.dumps(name)}: [{json.dumps(method)}, {json.dumps(path)}],"
        for name, (method, path) in items.items()
    )
    return (
        "// Generated from spec/openapi.json. Do not edit manually.\n\n"
        "export const operations = {\n"
        f"{rows}\n"
        "} as const\n\n"
        "export type OperationId = keyof typeof operations\n"
    )


def update(path: Path, content: str, *, check: bool) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return True
    if check:
        print(f"{path.relative_to(ROOT)} is stale")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    items = operations()
    valid = update(PYTHON_OUTPUT, python_source(items), check=args.check)
    valid &= update(
        TYPESCRIPT_OUTPUT, typescript_source(items), check=args.check
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
