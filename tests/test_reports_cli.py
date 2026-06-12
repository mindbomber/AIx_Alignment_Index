import json
from pathlib import Path

from aix.cli import main
from aix.reporting import csv_report, html_report, json_report, markdown_report
from aix.scoring import score_assessment


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "ai_output_assessment.yaml"


def test_report_formats(example_assessment):
    result = score_assessment(example_assessment)
    assert "# AIx Report" in markdown_report(result)
    assert json.loads(json_report(result))["adjusted_score"] == result.adjusted_score
    assert "domain,P," in csv_report(result)
    assert "<!doctype html>" in html_report(result)
    assert "ATS Dynamics Bridge" in markdown_report(result)


def test_cli_validate_score_and_report(tmp_path, capsys):
    assert main(["validate", str(EXAMPLE)]) == 0
    assert "Valid AIx assessment" in capsys.readouterr().out
    assert main(["score", str(EXAMPLE), "--json"]) == 0
    assert "adjusted_score" in capsys.readouterr().out
    output = tmp_path / "report.md"
    assert main(["report", str(EXAMPLE), "--out", str(output)]) == 0
    assert output.exists()
    assert "Parameter Disclosure" in output.read_text(encoding="utf-8")


def test_cli_compare_and_rubrics(tmp_path, capsys):
    comparison = tmp_path / "comparison.json"
    assert main(["compare", str(EXAMPLE), str(EXAMPLE), "--out", str(comparison)]) == 0
    assert json.loads(comparison.read_text())["adjusted_score_delta"] == 0
    assert main(["rubric", "list"]) == 0
    assert "core" in capsys.readouterr().out
    assert main(["rubric", "show", "core"]) == 0
    rubric_output = capsys.readouterr().out
    assert "AIx Core Rubric" in rubric_output
    assert "inheritance_resolved: true" in rubric_output
    assert rubric_output.count("code:") == 29


def test_cli_batch_and_html_report(tmp_path):
    batch = tmp_path / "batch.json"
    assert main(["batch", str(ROOT / "examples"), "--out", str(batch)]) == 0
    payload = json.loads(batch.read_text(encoding="utf-8"))
    assert len(payload) == 4
    output = tmp_path / "report.html"
    assert (
        main(
            [
                "report",
                str(EXAMPLE),
                "--format",
                "html",
                "--out",
                str(output),
            ]
        )
        == 0
    )
    assert "<!doctype html>" in output.read_text(encoding="utf-8")
    exported = tmp_path / "score.csv"
    assert (
        main(
            [
                "export",
                str(EXAMPLE),
                "--format",
                "csv",
                "--out",
                str(exported),
            ]
        )
        == 0
    )
    assert "adjusted_score" in exported.read_text(encoding="utf-8")


def test_cli_returns_two_for_invalid_file(capsys):
    assert main(["validate", "missing.yaml"]) == 2
    assert "No such file" in capsys.readouterr().err
