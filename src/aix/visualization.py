from __future__ import annotations

from pathlib import Path

from math import pi
from textwrap import fill

from .scoring import AIxResult


def _save(fig, destination: Path, stem: str, formats: tuple[str, ...]) -> list[Path]:
    outputs: list[Path] = []
    for output_format in formats:
        path = destination / f"{stem}.{output_format}"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        outputs.append(path)
    return outputs


def create_charts(
    result: AIxResult,
    output_dir: str | Path,
    *,
    formats: tuple[str, ...] = ("png", "svg"),
) -> list[Path]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Charts require the optional dependency: pip install 'aix-open[charts]'"
        ) from exc

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    name = str(result.system.get("name", "aix")).lower().replace(" ", "_")
    domains = list(result.domain_scores)
    values = [result.domain_scores[domain] for domain in domains]
    outputs: list[Path] = []

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(domains, values, color="#2563eb")
    ax.set_ylim(0, 100)
    ax.set_ylabel("Score")
    ax.set_title("AIx Domain Profile")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    outputs.extend(_save(fig, destination, f"{name}_domains", formats))
    plt.close(fig)

    angles = [index / len(domains) * 2 * pi for index in range(len(domains))]
    radar_values = values + values[:1]
    radar_angles = angles + angles[:1]
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={"polar": True})
    ax.plot(radar_angles, radar_values, color="#2563eb", linewidth=2)
    ax.fill(radar_angles, radar_values, color="#2563eb", alpha=0.2)
    ax.set_xticks(angles, domains)
    ax.set_ylim(0, 100)
    ax.set_title("AIx Radar Profile")
    outputs.extend(_save(fig, destination, f"{name}_radar", formats))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    codes = list(result.penalties)
    deductions = [result.penalties[code] for code in codes]
    ax.bar(codes, deductions, color="#dc2626")
    ax.set_ylabel("Points deducted")
    ax.set_title("AIx Penalty Breakdown")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    outputs.extend(_save(fig, destination, f"{name}_penalties", formats))
    plt.close(fig)
    return outputs


def create_comparison_charts(
    first: AIxResult,
    second: AIxResult,
    output_dir: str | Path,
    *,
    formats: tuple[str, ...] = ("png", "svg"),
) -> list[Path]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Charts require the optional dependency: pip install 'aix-open[charts]'"
        ) from exc
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    domains = list(first.domain_scores)
    positions = list(range(len(domains)))
    width = 0.36
    outputs: list[Path] = []

    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar(
        [position - width / 2 for position in positions],
        [first.domain_scores[d] for d in domains],
        width,
        label=first.system.get("name", "First"),
    )
    ax.bar(
        [position + width / 2 for position in positions],
        [second.domain_scores[d] for d in domains],
        width,
        label=second.system.get("name", "Second"),
    )
    ax.set_xticks(positions, domains)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Score")
    ax.set_title("AIx Before/After Domain Comparison")
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    outputs.extend(_save(fig, destination, "aix_before_after", formats))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4.5))
    labels = [
        fill(str(first.system.get("name", "First")), 22),
        fill(str(second.system.get("name", "Second")), 22),
    ]
    ax.bar(labels, [first.constraint_skew, second.constraint_skew], color=["#64748b", "#2563eb"])
    ax.axhline(15, color="#f59e0b", linestyle="--", label="moderate threshold")
    ax.axhline(30, color="#dc2626", linestyle="--", label="high threshold")
    ax.set_ylabel("Constraint skew")
    ax.set_title("AIx Skew Comparison")
    ax.legend()
    outputs.extend(_save(fig, destination, "aix_skew_comparison", formats))
    plt.close(fig)
    return outputs
