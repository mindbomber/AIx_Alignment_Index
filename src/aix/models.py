from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from jsonschema import Draft202012Validator

from .constants import (
    ALL_INDICATORS,
    DEFAULT_PENALTY_PARAMETERS,
    DOMAIN_INDICATORS,
)
from .io import data_directory


class AssessmentValidationError(ValueError):
    """Raised when an assessment cannot be scored as declared."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid AIx assessment:\n- " + "\n- ".join(errors))


def _system_metadata(data: Mapping[str, Any]) -> Mapping[str, Any]:
    system = data.get("system")
    return system if isinstance(system, Mapping) else data


def validate_assessment(
    assessment: Mapping[str, Any],
    *,
    require_complete: bool = True,
) -> list[str]:
    errors: list[str] = []
    schema_path = data_directory("spec") / "assessment.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_errors = sorted(
        Draft202012Validator(schema).iter_errors(dict(assessment)),
        key=lambda error: list(error.absolute_path),
    )
    for error in schema_errors:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")

    metadata = _system_metadata(assessment)
    name = metadata.get("name", assessment.get("system_name"))
    if not isinstance(name, str) or not name.strip():
        errors.append("system.name (or legacy system_name) is required")
    unit = metadata.get("unit_of_analysis", assessment.get("unit_of_analysis"))
    if not isinstance(unit, str) or not unit.strip():
        errors.append("system.unit_of_analysis (or legacy unit_of_analysis) is required")
    if isinstance(assessment.get("system"), Mapping):
        for field in ("reference_population", "time_horizon", "aggregation_rule"):
            value = metadata.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"system.{field} is required")

    scores = assessment.get("scores")
    if not isinstance(scores, Mapping):
        errors.append("scores must be an object keyed by indicator code")
        scores = {}

    unknown = sorted(set(scores) - set(ALL_INDICATORS))
    if unknown:
        errors.append(f"unknown indicator codes: {', '.join(unknown)}")
    if require_complete:
        missing = [code for code in ALL_INDICATORS if code not in scores]
        if missing:
            errors.append(f"missing required indicators: {', '.join(missing)}")

    for code, entry in scores.items():
        if code not in ALL_INDICATORS:
            continue
        if not isinstance(entry, Mapping):
            errors.append(f"{code} must be an object")
            continue
        score = entry.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 5:
            errors.append(f"{code}.score must be a number from 0 to 5")
        quality = entry.get("evidence_quality")
        if not isinstance(quality, (int, float)) or isinstance(quality, bool) or not 0 <= quality <= 1:
            errors.append(f"{code}.evidence_quality must be a number from 0 to 1")
        evidence = entry.get("evidence")
        notes = entry.get("notes")
        if not evidence and not notes:
            errors.append(f"{code} requires evidence or notes")

    weights = assessment.get("weights")
    if weights is not None:
        if not isinstance(weights, Mapping):
            errors.append("weights must be an object")
        else:
            if set(weights) != set(DOMAIN_INDICATORS):
                errors.append("weights must declare exactly P, B, CT, H, and F")
            values = list(weights.values())
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value < 0
                for value in values
            ):
                errors.append("weights must be non-negative numbers")
            elif abs(sum(values) - 1.0) > 1e-6:
                errors.append("weights must sum to 1.0")

    parameters = assessment.get("penalty_parameters", {})
    if not isinstance(parameters, Mapping):
        errors.append("penalty_parameters must be an object")
    else:
        unknown_parameters = sorted(set(parameters) - set(DEFAULT_PENALTY_PARAMETERS))
        if unknown_parameters:
            errors.append(
                f"unknown penalty parameters: {', '.join(unknown_parameters)}"
            )
        for key, value in parameters.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                errors.append(f"penalty parameter {key} must be non-negative")
        pi0 = parameters.get("pi0", DEFAULT_PENALTY_PARAMETERS["pi0"])
        pi_max = parameters.get("pi_max", DEFAULT_PENALTY_PARAMETERS["pi_max"])
        if isinstance(pi0, (int, float)) and not 0 <= pi0 <= 1:
            errors.append("penalty parameter pi0 must be between 0 and 1")
        if isinstance(pi_max, (int, float)) and pi_max <= 0:
            errors.append("penalty parameter pi_max must be greater than zero")

    pressure = assessment.get("optimization_pressure")
    if pressure is not None and (
        not isinstance(pressure, (int, float))
        or isinstance(pressure, bool)
        or not 0 <= pressure <= 1
    ):
        errors.append("optimization_pressure must be between 0 and 1")
    agreement = assessment.get("rater_agreement")
    if agreement is not None and (
        not isinstance(agreement, (int, float))
        or isinstance(agreement, bool)
        or not 0 <= agreement <= 1
    ):
        errors.append("rater_agreement must be between 0 and 1")
    domain_agreement = assessment.get("domain_agreement", {})
    if domain_agreement and set(domain_agreement) - set(DOMAIN_INDICATORS):
        errors.append("domain_agreement may contain only P, B, CT, H, and F")
    confidence_lambda = assessment.get("confidence_lambda")
    if confidence_lambda is not None and (
        not isinstance(confidence_lambda, (int, float))
        or isinstance(confidence_lambda, bool)
        or not 0 <= confidence_lambda <= 1
    ):
        errors.append("confidence_lambda must be between 0 and 1")

    if errors:
        raise AssessmentValidationError(errors)
    return []
