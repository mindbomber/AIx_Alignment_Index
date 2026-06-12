import copy

import pytest

from aix.models import AssessmentValidationError, validate_assessment


def test_complete_example_is_valid(example_assessment):
    assert validate_assessment(example_assessment) == []


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["scores"].pop("P1"), "missing required indicators"),
        (
            lambda data: data["scores"]["P1"].update(score=6),
            "P1.score must be a number from 0 to 5",
        ),
        (
            lambda data: data["scores"]["P1"].update(evidence_quality=-0.1),
            "P1.evidence_quality must be a number from 0 to 1",
        ),
        (
            lambda data: data.update(weights={"P": 1}),
            "weights must declare exactly",
        ),
        (
            lambda data: data.update(optimization_pressure=2),
            "optimization_pressure must be between 0 and 1",
        ),
    ],
)
def test_invalid_assessments_fail(example_assessment, mutation, message):
    data = copy.deepcopy(example_assessment)
    mutation(data)
    with pytest.raises(AssessmentValidationError, match=message):
        validate_assessment(data)


def test_partial_validation_can_be_requested(example_assessment):
    data = copy.deepcopy(example_assessment)
    data["scores"].pop("P1")
    assert validate_assessment(data, require_complete=False) == []

