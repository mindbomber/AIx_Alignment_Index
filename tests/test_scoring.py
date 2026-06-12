import copy

from pathlib import Path

from aix.io import load_document
from aix.scoring import compare_results, profile_distance, score_assessment


ROOT = Path(__file__).resolve().parents[1]


def test_score_produces_complete_diagnostic(example_assessment):
    result = score_assessment(example_assessment)
    assert set(result.domain_scores) == {"P", "B", "CT", "H", "F"}
    assert 0 <= result.adjusted_score <= result.raw_arithmetic <= 100
    assert result.raw_geometric <= 100
    assert result.constraint_skew > 15
    assert "proxy_capture" in result.failure_modes
    assert result.pressure_source == "declared"
    assert result.parameter_disclosure["theta_p"] == 15


def test_all_fives_score_one_hundred_without_penalty(example_assessment):
    data = copy.deepcopy(example_assessment)
    data.pop("optimization_pressure")
    for entry in data["scores"].values():
        entry["score"] = 5
        entry["evidence_quality"] = 1
    result = score_assessment(data)
    assert result.raw_arithmetic == 100
    assert result.raw_geometric == 100
    assert result.adjusted_score == 100
    assert result.total_penalty == 0
    assert result.optimization_pressure == 0


def test_penalties_trigger_for_proxy_heavy_low_layer_profile(example_assessment):
    data = copy.deepcopy(example_assessment)
    data["optimization_pressure"] = 1
    for code, entry in data["scores"].items():
        entry["score"] = 5 if code.startswith("C") else 1
        entry["evidence_quality"] = 1
    result = score_assessment(data)
    assert result.penalties["PCP"] > 0
    assert result.penalties["LVP"] > 0
    assert result.penalties["HEP"] > 0
    assert result.penalties["LEP"] > 0
    assert result.adjusted_score >= 0


def test_custom_parameters_and_rater_confidence(example_assessment):
    data = copy.deepcopy(example_assessment)
    data["penalty_parameters"] = {"eta_p": 0, "theta_l": 50}
    data["rater_agreement"] = 0.9
    result = score_assessment(data)
    assert result.penalties["PCP"] == 0
    assert result.parameter_disclosure["theta_l"] == 50
    assert result.confidence_basis.startswith("domain_evidence")
    assert set(result.domain_confidence) == {"P", "B", "CT", "H", "F"}


def test_compare_and_profile_distance(example_assessment):
    first = score_assessment(example_assessment)
    changed = copy.deepcopy(example_assessment)
    changed["system"]["name"] = "Improved"
    for entry in changed["scores"].values():
        entry["score"] = min(5, entry["score"] + 1)
    second = score_assessment(changed)
    comparison = compare_results(first, second)
    assert comparison["adjusted_score_delta"] > 0
    assert comparison["profile_distance_equal_weighted"] > 0
    assert comparison["profile_distance_lower_layer_weighted"] > 0
    assert profile_distance(first.domain_scores, first.domain_scores) == 0


def test_domain_floor_gate_score_band_and_dynamics(example_assessment):
    data = copy.deepcopy(example_assessment)
    data["domain_floors"] = {"P": 70, "B": 70, "F": 70}
    data["hidden_drift"] = 0.1
    result = score_assessment(data)
    assert result.mandatory_review is True
    assert len(result.review_reasons) == 3
    assert result.score_band == "fragile_mixed"
    assert result.dynamics_proxy["hidden_drift_proxy"] == 0.1
    assert "not a measured alignment rate" in result.dynamics_proxy["interpretation"]


def test_paper_worked_example_regression():
    result = score_assessment(
        load_document(ROOT / "examples" / "paper_worked_example.yaml")
    )
    expected = {"P": 60.95, "B": 57.62, "CT": 80.82, "H": 43.03, "F": 56.82}
    assert result.domain_scores == expected
    assert abs(result.constraint_skew - 22.36) < 0.02
    assert abs(result.penalties["PCP"] - 3.25) < 0.05
    assert abs(result.penalties["HEP"] - 0.42) < 0.02
    assert abs(result.adjusted_score - 56.18) < 0.1
