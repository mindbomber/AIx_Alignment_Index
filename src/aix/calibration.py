from __future__ import annotations

import copy
import csv
from dataclasses import asdict, dataclass
from hashlib import sha256
from math import sqrt
from pathlib import Path
from statistics import fmean
from typing import Any

from .constants import DEFAULT_PENALTY_PARAMETERS
from .io import load_document
from .scoring import score_assessment


REQUIRED_COLUMNS = {
    "case_id",
    "assessment",
    "split",
    "observed_incident",
    "expert_score",
}


@dataclass(frozen=True)
class ValidationMetrics:
    cases: int
    incident_rate: float
    mean_absolute_error: float
    pearson_correlation: float | None
    roc_auc: float | None
    brier_score: float
    sensitivity: float | None
    specificity: float | None


@dataclass(frozen=True)
class CalibrationReport:
    dataset_sha256: str
    selected_penalty_scale: float
    selected_incident_threshold: float
    training: ValidationMetrics
    validation: ValidationMetrics
    calibrated_parameters: dict[str, float]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_calibration_cases(path: str | Path) -> list[dict[str, Any]]:
    source_path = Path(path)
    with source_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError("Calibration dataset is empty.")
    missing = REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise ValueError(f"Missing calibration columns: {', '.join(sorted(missing))}")
    cases = []
    seen: set[str] = set()
    for row in rows:
        case_id = row["case_id"].strip()
        if not case_id or case_id in seen:
            raise ValueError("Calibration case_id values must be non-empty and unique.")
        seen.add(case_id)
        split = row["split"].strip().lower()
        if split not in {"train", "validation"}:
            raise ValueError("Calibration split must be train or validation.")
        incident = int(row["observed_incident"])
        expert_score = float(row["expert_score"])
        if incident not in {0, 1}:
            raise ValueError("observed_incident must be 0 or 1.")
        if not 0 <= expert_score <= 100:
            raise ValueError("expert_score must be between 0 and 100.")
        assessment_path = (source_path.parent / row["assessment"]).resolve()
        if not assessment_path.is_file():
            raise ValueError(f"Assessment file does not exist: {assessment_path}")
        cases.append(
            {
                **row,
                "case_id": case_id,
                "split": split,
                "observed_incident": incident,
                "expert_score": expert_score,
                "assessment_path": assessment_path,
            }
        )
    if not any(case["split"] == "train" for case in cases):
        raise ValueError("Calibration dataset requires train cases.")
    if not any(case["split"] == "validation" for case in cases):
        raise ValueError("Calibration dataset requires validation cases.")
    return cases


def _score_cases(cases: list[dict[str, Any]], penalty_scale: float) -> list[dict[str, Any]]:
    scored = []
    for case in cases:
        assessment = copy.deepcopy(load_document(case["assessment_path"]))
        parameters = dict(DEFAULT_PENALTY_PARAMETERS)
        parameters.update(assessment.get("penalty_parameters", {}))
        for parameter in ("eta_p", "eta_l", "eta_h", "eta_e"):
            parameters[parameter] *= penalty_scale
        assessment["penalty_parameters"] = parameters
        result = score_assessment(assessment)
        scored.append({**case, "adjusted_score": result.adjusted_score})
    return scored


def _pearson(first: list[float], second: list[float]) -> float | None:
    if len(first) < 2:
        return None
    first_mean, second_mean = fmean(first), fmean(second)
    numerator = sum(
        (a - first_mean) * (b - second_mean) for a, b in zip(first, second)
    )
    denominator = sqrt(
        sum((a - first_mean) ** 2 for a in first)
        * sum((b - second_mean) ** 2 for b in second)
    )
    return numerator / denominator if denominator else None


def _auc(labels: list[int], risks: list[float]) -> float | None:
    positives = [risk for label, risk in zip(labels, risks) if label == 1]
    negatives = [risk for label, risk in zip(labels, risks) if label == 0]
    if not positives or not negatives:
        return None
    favorable = sum(
        1 if positive > negative else 0.5 if positive == negative else 0
        for positive in positives
        for negative in negatives
    )
    return favorable / (len(positives) * len(negatives))


def _metrics(cases: list[dict[str, Any]], threshold: float) -> ValidationMetrics:
    scores = [float(case["adjusted_score"]) for case in cases]
    expert = [float(case["expert_score"]) for case in cases]
    labels = [int(case["observed_incident"]) for case in cases]
    risks = [(100 - score) / 100 for score in scores]
    predicted = [score < threshold for score in scores]
    positives = sum(labels)
    negatives = len(labels) - positives
    true_positives = sum(label == 1 and prediction for label, prediction in zip(labels, predicted))
    true_negatives = sum(label == 0 and not prediction for label, prediction in zip(labels, predicted))
    return ValidationMetrics(
        cases=len(cases),
        incident_rate=round(fmean(labels), 4),
        mean_absolute_error=round(
            fmean(abs(score - target) for score, target in zip(scores, expert)), 4
        ),
        pearson_correlation=(
            None
            if (correlation := _pearson(scores, expert)) is None
            else round(correlation, 4)
        ),
        roc_auc=(
            None if (auc := _auc(labels, risks)) is None else round(auc, 4)
        ),
        brier_score=round(
            fmean((risk - label) ** 2 for risk, label in zip(risks, labels)), 4
        ),
        sensitivity=(
            round(true_positives / positives, 4) if positives else None
        ),
        specificity=(
            round(true_negatives / negatives, 4) if negatives else None
        ),
    )


def calibrate_dataset(path: str | Path) -> CalibrationReport:
    source_path = Path(path)
    cases = read_calibration_cases(source_path)
    training = [case for case in cases if case["split"] == "train"]
    validation = [case for case in cases if case["split"] == "validation"]
    candidates = []
    for scale in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        scored = _score_cases(training, scale)
        for threshold in range(30, 81, 5):
            metrics = _metrics(scored, float(threshold))
            classification_loss = (
                (1 - (metrics.sensitivity or 0))
                + (1 - (metrics.specificity or 0))
            )
            objective = metrics.mean_absolute_error + 10 * classification_loss
            candidates.append((objective, scale, float(threshold), metrics))
    _, scale, threshold, training_metrics = min(candidates, key=lambda item: item[0])
    validation_metrics = _metrics(_score_cases(validation, scale), threshold)
    first_assessment = load_document(training[0]["assessment_path"])
    parameters = dict(DEFAULT_PENALTY_PARAMETERS)
    parameters.update(first_assessment.get("penalty_parameters", {}))
    for parameter in ("eta_p", "eta_l", "eta_h", "eta_e"):
        parameters[parameter] = round(parameters[parameter] * scale, 6)
    return CalibrationReport(
        dataset_sha256=sha256(source_path.read_bytes()).hexdigest(),
        selected_penalty_scale=scale,
        selected_incident_threshold=threshold,
        training=training_metrics,
        validation=validation_metrics,
        calibrated_parameters=parameters,
        limitations=[
            "Calibration is only as valid as the case labels, sampling frame, and rater independence.",
            "Use externally collected holdout cases before consequential deployment.",
            "Do not treat a small development benchmark as empirical certification.",
        ],
    )


def calibration_markdown(report: CalibrationReport) -> str:
    lines = [
        "# AIx Calibration Report",
        "",
        f"- Dataset SHA-256: `{report.dataset_sha256}`",
        f"- Selected penalty scale: {report.selected_penalty_scale}",
        f"- Incident threshold: {report.selected_incident_threshold}",
        "",
        "| Split | Cases | MAE | Correlation | ROC AUC | Brier | Sensitivity | Specificity |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in (
        ("Training", report.training),
        ("Validation", report.validation),
    ):
        lines.append(
            f"| {name} | {metrics.cases} | {metrics.mean_absolute_error} | "
            f"{metrics.pearson_correlation} | {metrics.roc_auc} | "
            f"{metrics.brier_score} | {metrics.sensitivity} | {metrics.specificity} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    return "\n".join(lines) + "\n"
