from __future__ import annotations

import csv
import html
import io
import json
from typing import Any

from .constants import DOMAIN_NAMES
from .scoring import AIxResult


def markdown_report(result: AIxResult) -> str:
    name = result.system.get("name", "Unnamed system")
    lines = [
        f"# AIx Report: {name}",
        "",
        "## Executive Summary",
        "",
        f"- Adjusted AIx: **{result.adjusted_score:.2f} / 100**",
        f"- Raw arithmetic AIx: **{result.raw_arithmetic:.2f}**",
        f"- Raw geometric AIx: **{result.raw_geometric:.2f}**",
        f"- Constraint skew: **{result.constraint_skew:.2f}** ({result.skew_category})",
        f"- Confidence: **{result.confidence:.3f}** ({result.confidence_basis})",
        f"- Decision band: **{result.score_band}**",
        f"- Mandatory review: **{'yes' if result.mandatory_review else 'no'}**",
        "",
        "AIx is interpreted vector-first: domain scores, evidence, and hard lower-layer "
        "concerns take priority over the composite.",
        "",
        "## System Metadata",
        "",
    ]
    for key, value in result.system.items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    lines.extend(
        [
            "",
            "## Domain Profile",
            "",
            "| Domain | Score | Evidence quality | Weight |",
            "|---|---:|---:|---:|",
        ]
    )
    for domain, label in DOMAIN_NAMES.items():
        lines.append(
            f"| {domain} - {label} | {result.domain_scores[domain]:.2f} | "
            f"{result.domain_evidence_quality[domain]:.3f} | {result.weights[domain]:.3f} |"
        )
    lines.extend(["", "### Domain Confidence", ""])
    for domain, value in result.domain_confidence.items():
        lines.append(f"- **{domain}:** {value:.3f}")
    lines.extend(
        [
            "",
            f"**Balance range:** {result.balance_range:.2f} ({result.balance_category})",
            "",
            "## Penalty Breakdown",
            "",
            "| Penalty | Deduction |",
            "|---|---:|",
        ]
    )
    for code, value in result.penalties.items():
        lines.append(f"| {code} | {value:.2f} |")
    lines.extend(
        [
            "",
            f"**Total penalty:** {result.total_penalty:.2f}",
            f"**Optimization pressure:** {result.optimization_pressure:.3f} "
            f"({result.pressure_source})",
            f"**Decision interpretation:** {result.score_interpretation}",
            "",
            "## Failure-Mode Diagnosis",
            "",
        ]
    )
    lines.extend(f"- `{mode}`" for mode in result.failure_modes)
    if result.review_reasons:
        lines.extend(["", "### Mandatory Review Reasons", ""])
        lines.extend(f"- {reason}" for reason in result.review_reasons)
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in result.recommendations)
    lines.extend(["", "## Parameter Disclosure", "", "| Parameter | Value |", "|---|---:|"])
    for key, value in result.parameter_disclosure.items():
        lines.append(f"| `{key}` | {value:g} |")
    lines.extend(
        [
            "",
            "## ATS Dynamics Bridge",
            "",
            f"**Directional estimate:** {result.dynamics_proxy['estimate']}",
            "",
            result.dynamics_proxy["interpretation"],
        ]
    )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in result.limitations)
    return "\n".join(lines) + "\n"


def json_report(result: AIxResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n"


def csv_report(result: AIxResult) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["section", "metric", "value"])
    for domain, value in result.domain_scores.items():
        writer.writerow(["domain", domain, value])
    writer.writerow(["composite", "raw_arithmetic", result.raw_arithmetic])
    writer.writerow(["composite", "raw_geometric", result.raw_geometric])
    writer.writerow(["composite", "adjusted_score", result.adjusted_score])
    writer.writerow(["diagnostic", "constraint_skew", result.constraint_skew])
    writer.writerow(["diagnostic", "confidence", result.confidence])
    writer.writerow(["diagnostic", "score_band", result.score_band])
    writer.writerow(["diagnostic", "mandatory_review", result.mandatory_review])
    writer.writerow(
        ["diagnostic", "dynamics_proxy", result.dynamics_proxy["estimate"]]
    )
    for code, value in result.penalties.items():
        writer.writerow(["penalty", code, value])
    return output.getvalue()


def render_report(result: AIxResult, output_format: str) -> str:
    renderers: dict[str, Any] = {
        "markdown": markdown_report,
        "md": markdown_report,
        "json": json_report,
        "csv": csv_report,
        "html": html_report,
    }
    try:
        return renderers[output_format.lower()](result)
    except KeyError as exc:
        raise ValueError(f"Unsupported report format: {output_format}") from exc


def html_report(result: AIxResult) -> str:
    markdown = markdown_report(result)
    body = html.escape(markdown)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>AIx Report</title><style>"
        "body{max-width:900px;margin:2rem auto;font:16px/1.5 system-ui;color:#172033}"
        "pre{white-space:pre-wrap;background:#f6f8fa;padding:1.25rem;border-radius:8px}"
        "</style></head><body><pre>"
        f"{body}</pre></body></html>\n"
    )
