from __future__ import annotations

import argparse
import json
from pathlib import Path

from aix_platform.app import create_app


def render_openapi() -> str:
    return json.dumps(create_app(create_schema=False).openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the AIx Platform OpenAPI contract")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", default="spec/openapi.json")
    args = parser.parse_args()
    destination = Path(args.out)
    rendered = render_openapi()
    if args.check:
        if not destination.is_file() or destination.read_text(encoding="utf-8") != rendered:
            raise SystemExit(
                f"{destination} is stale; run python scripts/export_openapi.py"
            )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
