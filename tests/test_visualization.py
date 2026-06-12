from pathlib import Path

from aix.io import load_document
from aix.scoring import score_assessment
from aix.visualization import create_charts, create_comparison_charts


ROOT = Path(__file__).resolve().parents[1]


def test_all_chart_types_and_formats(tmp_path):
    first = score_assessment(
        load_document(ROOT / "examples" / "ai_output_assessment.yaml")
    )
    second = score_assessment(
        load_document(ROOT / "examples" / "institution_assessment.yaml")
    )
    outputs = create_charts(first, tmp_path)
    comparisons = create_comparison_charts(first, second, tmp_path)
    assert len(outputs) == 6
    assert len(comparisons) == 4
    assert {path.suffix for path in outputs + comparisons} == {".png", ".svg"}
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs + comparisons)

