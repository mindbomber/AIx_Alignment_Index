import json
from pathlib import Path

import yaml

from aix.rubrics import load_rubric


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_indicator_spec_is_complete():
    data = yaml.safe_load((ROOT / "spec" / "indicators.yaml").read_text())
    indicators = [
        indicator
        for domain in data["domains"].values()
        for indicator in domain["indicators"].values()
    ]
    assert len(indicators) == 29
    assert all(
        {"name", "question", "evidence_examples"} <= set(item)
        for item in indicators
    )


def test_resolved_rubric_contains_full_instrument():
    rubric = load_rubric("ai_systems")
    indicators = [
        indicator
        for domain in rubric["domains"].values()
        for indicator in domain["indicators"].values()
    ]
    assert len(indicators) == 29
    assert all("scale" in indicator for indicator in indicators)
    assert "contextual_anchors" in rubric["domains"]["P"]["indicators"]["P1"]


def test_notebook_is_valid_and_code_cells_compile():
    notebook = json.loads(
        (ROOT / "notebooks" / "example_assessment.ipynb").read_text(encoding="utf-8")
    )
    assert notebook["nbformat"] == 4
    code_cells = [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ]
    assert code_cells
    for source in code_cells:
        compile(source, "<notebook>", "exec")
