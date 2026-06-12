from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from statistics import fmean, pstdev
from typing import Iterable


@dataclass(frozen=True)
class ReliabilitySummary:
    observations: int
    systems: int
    raters: int
    indicators: int
    mean_score: float
    standard_deviation: float
    mean_absolute_disagreement: float
    agreement_within_one: float
    quadratic_weighted_kappa: float | None
    icc_2_1: float | None
    cronbach_alpha: float | None
    confidence_lambda: float
    domain_details: list[dict[str, object]]
    group_details: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def read_ratings_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    required = {"rater_id", "system_id", "indicator", "score"}
    if not rows:
        raise ValueError("Reliability input is empty.")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Missing reliability columns: {', '.join(sorted(missing))}")
    return rows


def analyze_reliability(rows: Iterable[dict[str, str]]) -> ReliabilitySummary:
    materialized = list(rows)
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    ratings_by_item: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    raters: set[str] = set()
    systems: set[str] = set()
    indicators: set[str] = set()
    all_scores: list[float] = []
    for row in materialized:
        score = float(row["score"])
        if not 0 <= score <= 5:
            raise ValueError("Reliability scores must be between 0 and 5.")
        key = (row["system_id"], row["indicator"])
        groups[key].append(score)
        ratings_by_item[key][row["rater_id"]] = score
        raters.add(row["rater_id"])
        systems.add(row["system_id"])
        indicators.add(row["indicator"])
        all_scores.append(score)

    pair_differences: list[float] = []
    details: list[dict[str, object]] = []
    for (system_id, indicator), scores in sorted(groups.items()):
        differences = [abs(a - b) for a, b in combinations(scores, 2)]
        pair_differences.extend(differences)
        details.append(
            {
                "system_id": system_id,
                "indicator": indicator,
                "raters": len(scores),
                "mean": round(fmean(scores), 3),
                "standard_deviation": round(pstdev(scores), 3),
                "mean_absolute_disagreement": (
                    round(fmean(differences), 3) if differences else 0.0
                ),
                "agreement_within_one": (
                    round(sum(d <= 1 for d in differences) / len(differences), 3)
                    if differences
                    else 1.0
                ),
                "confidence": round(
                    0.25
                    + 0.5
                    * (
                        sum(d <= 1 for d in differences) / len(differences)
                        if differences
                        else 1.0
                    ),
                    3,
                ),
            }
        )
    kappa = _mean_pairwise_weighted_kappa(ratings_by_item, sorted(raters))
    icc = _icc_2_1(ratings_by_item, sorted(raters))
    alpha = _cronbach_alpha(ratings_by_item, sorted(raters))
    domain_pairs: dict[str, list[float]] = defaultdict(list)
    domain_scores: dict[str, list[float]] = defaultdict(list)
    for (system_id, indicator), scores in sorted(groups.items()):
        del system_id
        domain = "CT" if indicator.startswith("C") else indicator[0]
        domain_scores[domain].extend(scores)
        domain_pairs[domain].extend(abs(a - b) for a, b in combinations(scores, 2))
    domain_details = []
    for domain in sorted(domain_scores):
        differences = domain_pairs[domain]
        agreement = (
            sum(value <= 1 for value in differences) / len(differences)
            if differences
            else 1.0
        )
        domain_details.append(
            {
                "domain": domain,
                "standard_deviation": round(pstdev(domain_scores[domain]), 3),
                "mean_absolute_disagreement": (
                    round(fmean(differences), 3) if differences else 0.0
                ),
                "agreement_within_one": round(agreement, 3),
                "confidence_with_neutral_evidence": round(0.25 + 0.5 * agreement, 3),
            }
        )
    return ReliabilitySummary(
        observations=len(materialized),
        systems=len(systems),
        raters=len(raters),
        indicators=len(indicators),
        mean_score=round(fmean(all_scores), 3),
        standard_deviation=round(pstdev(all_scores), 3),
        mean_absolute_disagreement=(
            round(fmean(pair_differences), 3) if pair_differences else 0.0
        ),
        agreement_within_one=(
            round(sum(d <= 1 for d in pair_differences) / len(pair_differences), 3)
            if pair_differences
            else 1.0
        ),
        quadratic_weighted_kappa=None if kappa is None else round(kappa, 3),
        icc_2_1=None if icc is None else round(icc, 3),
        cronbach_alpha=None if alpha is None else round(alpha, 3),
        confidence_lambda=0.5,
        domain_details=domain_details,
        group_details=details,
    )


def _quadratic_weighted_kappa(first: list[float], second: list[float]) -> float | None:
    if len(first) != len(second) or not first:
        return None
    categories = range(6)
    observed = [[0.0 for _ in categories] for _ in categories]
    for a, b in zip(first, second):
        observed[round(a)][round(b)] += 1
    first_counts = [sum(row) for row in observed]
    second_counts = [sum(observed[i][j] for i in categories) for j in categories]
    total = float(len(first))
    observed_cost = 0.0
    expected_cost = 0.0
    for i in categories:
        for j in categories:
            weight = ((i - j) / 5.0) ** 2
            observed_cost += weight * observed[i][j] / total
            expected_cost += weight * (first_counts[i] * second_counts[j]) / total**2
    if expected_cost == 0:
        return 1.0 if observed_cost == 0 else None
    return 1.0 - observed_cost / expected_cost


def _mean_pairwise_weighted_kappa(
    ratings: dict[tuple[str, str], dict[str, float]], raters: list[str]
) -> float | None:
    values: list[float] = []
    for first_rater, second_rater in combinations(raters, 2):
        paired = [
            (item[first_rater], item[second_rater])
            for item in ratings.values()
            if first_rater in item and second_rater in item
        ]
        if paired:
            value = _quadratic_weighted_kappa(
                [pair[0] for pair in paired], [pair[1] for pair in paired]
            )
            if value is not None:
                values.append(value)
    return fmean(values) if values else None


def _icc_2_1(
    ratings: dict[tuple[str, str], dict[str, float]], raters: list[str]
) -> float | None:
    matrix = [
        [item[rater] for rater in raters]
        for item in ratings.values()
        if all(rater in item for rater in raters)
    ]
    n = len(matrix)
    k = len(raters)
    if n < 2 or k < 2:
        return None
    grand = fmean(value for row in matrix for value in row)
    row_means = [fmean(row) for row in matrix]
    col_means = [fmean(row[j] for row in matrix) for j in range(k)]
    ms_rows = k * sum((mean - grand) ** 2 for mean in row_means) / (n - 1)
    ms_cols = n * sum((mean - grand) ** 2 for mean in col_means) / (k - 1)
    residual = sum(
        (matrix[i][j] - row_means[i] - col_means[j] + grand) ** 2
        for i in range(n)
        for j in range(k)
    )
    ms_error = residual / ((n - 1) * (k - 1))
    denominator = ms_rows + (k - 1) * ms_error + k * (ms_cols - ms_error) / n
    return (ms_rows - ms_error) / denominator if denominator else None


def _cronbach_alpha(
    ratings: dict[tuple[str, str], dict[str, float]], raters: list[str]
) -> float | None:
    items = [
        item for item in ratings.values() if all(rater in item for rater in raters)
    ]
    if len(items) < 2 or len(raters) < 2:
        return None
    matrix = [[item[rater] for item in items] for rater in raters]
    item_variances = [pstdev([row[j] for row in matrix]) ** 2 for j in range(len(items))]
    totals = [sum(row) for row in matrix]
    total_variance = pstdev(totals) ** 2
    if total_variance == 0:
        return None
    count = len(items)
    return count / (count - 1) * (1 - sum(item_variances) / total_variance)


def reliability_markdown(result: ReliabilitySummary) -> str:
    lines = [
        "# AIx Reliability Report",
        "",
        f"- Observations: {result.observations}",
        f"- Raters: {result.raters}",
        f"- Mean absolute disagreement: {result.mean_absolute_disagreement}",
        f"- Agreement within one point: {result.agreement_within_one}",
        f"- Quadratic weighted kappa: {result.quadratic_weighted_kappa}",
        f"- ICC(2,1): {result.icc_2_1}",
        f"- Cronbach alpha: {result.cronbach_alpha}",
        "",
        "## Domain Diagnostics",
        "",
        "| Domain | SD | MAD | Within 1 | Confidence |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in result.domain_details:
        lines.append(
            f"| {item['domain']} | {item['standard_deviation']} | "
            f"{item['mean_absolute_disagreement']} | {item['agreement_within_one']} | "
            f"{item['confidence_with_neutral_evidence']} |"
        )
    lines.extend(
        [
        "",
        "## Indicator Diagnostics",
        "",
        "| System | Indicator | Raters | Mean | SD | MAD | Within 1 | Confidence |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in result.group_details:
        lines.append(
            f"| {item['system_id']} | {item['indicator']} | {item['raters']} | "
            f"{item['mean']} | {item['standard_deviation']} | "
            f"{item['mean_absolute_disagreement']} | {item['agreement_within_one']} | "
            f"{item['confidence']} |"
        )
    return "\n".join(lines) + "\n"
