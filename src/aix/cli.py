from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .calibration import calibrate_dataset, calibration_markdown
from .io import load_document, write_text
from .models import AssessmentValidationError, validate_assessment
from .reliability import analyze_reliability, read_ratings_csv, reliability_markdown
from .reporting import render_report
from .rubrics import list_rubrics, load_rubric
from .scoring import compare_results, score_assessment
from .visualization import create_charts, create_comparison_charts


def _score(path: str):
    return score_assessment(load_document(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aix", description="AIx Open measurement framework"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate an assessment")
    validate.add_argument("assessment")
    validate.add_argument("--allow-partial", action="store_true")

    score = subparsers.add_parser("score", help="Score an assessment")
    score.add_argument("assessment")
    score.add_argument("--json", action="store_true", dest="as_json")
    score.add_argument(
        "--format", choices=["summary", "markdown", "json", "csv", "html"], default="summary"
    )

    report = subparsers.add_parser("report", help="Generate a report")
    report.add_argument("assessment")
    report.add_argument(
        "--format", choices=["markdown", "json", "csv", "html"], default="markdown"
    )
    report.add_argument("--out")

    compare = subparsers.add_parser("compare", help="Compare two assessments")
    compare.add_argument("first")
    compare.add_argument("second")
    compare.add_argument("--out")

    rubric = subparsers.add_parser("rubric", help="Inspect bundled rubrics")
    rubric_subparsers = rubric.add_subparsers(dest="rubric_command", required=True)
    rubric_subparsers.add_parser("list")
    rubric_show = rubric_subparsers.add_parser("show")
    rubric_show.add_argument("name")

    reliability = subparsers.add_parser(
        "reliability", help="Analyze multi-rater CSV data"
    )
    reliability.add_argument("ratings")
    reliability.add_argument("--out")
    reliability.add_argument("--format", choices=["json", "markdown"], default="json")

    calibration = subparsers.add_parser(
        "calibrate", help="Calibrate penalties and validate criterion outcomes"
    )
    calibration.add_argument("dataset")
    calibration.add_argument("--out")
    calibration.add_argument("--format", choices=["json", "markdown"], default="json")

    chart = subparsers.add_parser("chart", help="Generate publication-friendly charts")
    chart.add_argument("assessment")
    chart.add_argument("comparison", nargs="?")
    chart.add_argument("--out-dir", default="charts")
    chart.add_argument("--format", choices=["png", "svg", "both"], default="both")

    batch = subparsers.add_parser("batch", help="Score every YAML/JSON assessment in a directory")
    batch.add_argument("directory")
    batch.add_argument("--out")

    export = subparsers.add_parser("export", help="Export a score as JSON or CSV")
    export.add_argument("assessment")
    export.add_argument("--format", choices=["json", "csv"], default="csv")
    export.add_argument("--out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            data = load_document(args.assessment)
            validate_assessment(data, require_complete=not args.allow_partial)
            print(f"Valid AIx assessment: {args.assessment}")
        elif args.command == "score":
            result = _score(args.assessment)
            output_format = "json" if args.as_json else args.format
            if output_format != "summary":
                print(render_report(result, output_format), end="")
            else:
                review = " mandatory-review" if result.mandatory_review else ""
                print(
                    f"{result.system.get('name')}: adjusted={result.adjusted_score:.2f}, "
                    f"raw={result.raw_arithmetic:.2f}, skew={result.constraint_skew:.2f} "
                    f"({result.skew_category}), band={result.score_band}{review}"
                )
        elif args.command == "report":
            content = render_report(_score(args.assessment), args.format)
            if args.out:
                print(write_text(args.out, content))
            else:
                print(content, end="")
        elif args.command == "compare":
            content = json.dumps(
                compare_results(_score(args.first), _score(args.second)), indent=2
            ) + "\n"
            if args.out:
                print(write_text(args.out, content))
            else:
                print(content, end="")
        elif args.command == "rubric":
            if args.rubric_command == "list":
                print("\n".join(list_rubrics()))
            else:
                print(yaml.safe_dump(load_rubric(args.name), sort_keys=False))
        elif args.command == "reliability":
            result = analyze_reliability(read_ratings_csv(args.ratings))
            content = (
                reliability_markdown(result)
                if args.format == "markdown"
                else json.dumps(result.to_dict(), indent=2) + "\n"
            )
            if args.out:
                print(write_text(args.out, content))
            else:
                print(content, end="")
        elif args.command == "calibrate":
            result = calibrate_dataset(args.dataset)
            content = (
                calibration_markdown(result)
                if args.format == "markdown"
                else json.dumps(result.to_dict(), indent=2) + "\n"
            )
            if args.out:
                print(write_text(args.out, content))
            else:
                print(content, end="")
        elif args.command == "chart":
            formats = ("png", "svg") if args.format == "both" else (args.format,)
            if args.comparison:
                paths = create_comparison_charts(
                    _score(args.assessment),
                    _score(args.comparison),
                    args.out_dir,
                    formats=formats,
                )
            else:
                paths = create_charts(
                    _score(args.assessment), args.out_dir, formats=formats
                )
            for path in paths:
                print(path)
        elif args.command == "batch":
            directory = Path(args.directory)
            paths = sorted(
                path
                for path in directory.iterdir()
                if path.suffix.lower() in {".yaml", ".yml", ".json"}
            )
            results = [_score(str(path)).to_dict() for path in paths]
            content = json.dumps(results, indent=2) + "\n"
            if args.out:
                print(write_text(args.out, content))
            else:
                print(content, end="")
        elif args.command == "export":
            content = render_report(_score(args.assessment), args.format)
            print(write_text(args.out, content))
        return 0
    except (AssessmentValidationError, ValueError, FileNotFoundError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
