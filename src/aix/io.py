from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import yaml


def load_document(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        data = json.loads(text)
    elif source.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        raise ValueError(f"Unsupported file type: {source.suffix or '<none>'}")
    if not isinstance(data, dict):
        raise ValueError("Assessment document must contain a top-level object.")
    return data


def write_text(path: str | Path, content: str) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination


def data_directory(name: str) -> Path:
    candidates = [
        Path.cwd() / name,
        Path(__file__).resolve().parents[2] / name,
        Path(sys.prefix) / "share" / "aix" / name,
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate the {name} data directory.")
