from __future__ import annotations

from typing import Any, Mapping


def evaluate_policy(
    result: Mapping[str, Any],
    rules: Mapping[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    minimum_adjusted = float(rules.get("minimum_adjusted_score", 0))
    if float(result["adjusted_score"]) < minimum_adjusted:
        failures.append(
            f"adjusted_score {result['adjusted_score']} is below {minimum_adjusted}"
        )

    minimum_confidence = float(rules.get("minimum_confidence", 0))
    if float(result["confidence"]) < minimum_confidence:
        failures.append(
            f"confidence {result['confidence']} is below {minimum_confidence}"
        )

    minimum_evidence = float(rules.get("minimum_evidence_quality", 0))
    if float(result["evidence_quality"]) < minimum_evidence:
        failures.append(
            f"evidence_quality {result['evidence_quality']} is below {minimum_evidence}"
        )

    for domain, threshold in rules.get("domain_minimums", {}).items():
        score = float(result["domain_scores"].get(domain, 0))
        if score < float(threshold):
            failures.append(f"domain {domain} score {score} is below {threshold}")

    if rules.get("reject_mandatory_review", False) and result["mandatory_review"]:
        failures.append("assessment requires mandatory review")

    blocked_modes = set(rules.get("blocked_failure_modes", []))
    present_modes = blocked_modes.intersection(result["failure_modes"])
    if present_modes:
        failures.append(
            "blocked failure modes present: " + ", ".join(sorted(present_modes))
        )

    return {
        "outcome": "pass" if not failures else "fail",
        "failures": failures,
        "rules": dict(rules),
    }
