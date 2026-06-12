from pathlib import Path

import pytest

from aix.io import load_document
from aix.reliability import analyze_reliability, read_ratings_csv


ROOT = Path(__file__).resolve().parents[1]


def test_reliability_summary():
    rows = read_ratings_csv(ROOT / "examples" / "multi_rater_scores.csv")
    result = analyze_reliability(rows)
    assert result.raters == 3
    assert result.indicators == 3
    assert 0 <= result.agreement_within_one <= 1
    assert result.mean_absolute_disagreement > 0
    assert result.quadratic_weighted_kappa is not None
    assert result.icc_2_1 is not None
    assert result.cronbach_alpha is not None
    assert result.domain_details
    assert all("confidence" in detail for detail in result.group_details)


def test_reliability_rejects_invalid_score():
    with pytest.raises(ValueError, match="between 0 and 5"):
        analyze_reliability(
            [{"rater_id": "r1", "system_id": "s", "indicator": "P1", "score": "9"}]
        )


def test_load_document_rejects_unsupported_extension(tmp_path):
    source = tmp_path / "assessment.txt"
    source.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_document(source)
