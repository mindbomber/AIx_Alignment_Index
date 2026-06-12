from __future__ import annotations

from typing import Any

import yaml

from .io import data_directory


def list_rubrics() -> list[str]:
    return sorted(path.stem for path in data_directory("rubrics").glob("*.yaml"))


def load_rubric(name: str, *, resolve: bool = True) -> dict[str, Any]:
    path = data_directory("rubrics") / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Unknown rubric: {name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Rubric {name} is not a YAML object.")
    if not resolve:
        return data
    indicators = yaml.safe_load(
        (data_directory("spec") / "indicators.yaml").read_text(encoding="utf-8")
    )
    scale = yaml.safe_load(
        (data_directory("spec") / "scoring_scale.yaml").read_text(encoding="utf-8")
    )
    resolved: dict[str, Any] = {
        **data,
        "canonical_scale": scale["scale"],
        "domains": indicators["domains"],
    }
    overrides = data.get("anchors", {})
    for domain in resolved["domains"].values():
        for code, indicator in domain["indicators"].items():
            indicator["code"] = code
            indicator["scale"] = scale["scale"]
            if code in overrides:
                indicator["contextual_anchors"] = overrides[code]
    resolved["inheritance_resolved"] = True
    return resolved
    return data
