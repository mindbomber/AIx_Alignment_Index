from pathlib import Path

import pytest

from aix.calibration import (
    calibrate_dataset,
    calibration_markdown,
    read_calibration_cases,
)
from aix.cli import main


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "development" / "criterion_cases.csv"


def test_calibration_pipeline_has_untouched_validation_metrics(tmp_path):
    report = calibrate_dataset(DATASET)
    assert report.training.cases == 2
    assert report.validation.cases == 2
    assert report.validation.roc_auc is not None
    assert len(report.dataset_sha256) == 64
    assert report.calibrated_parameters["eta_p"] >= 0
    assert "Validation" in calibration_markdown(report)
    output = tmp_path / "calibration.json"
    assert main(["calibrate", str(DATASET), "--out", str(output)]) == 0
    assert '"dataset_sha256"' in output.read_text(encoding="utf-8")


def test_calibration_dataset_rejects_invalid_split(tmp_path):
    source = tmp_path / "cases.csv"
    source.write_text(
        "case_id,assessment,split,observed_incident,expert_score\n"
        "x,missing.yaml,test,0,50\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="split"):
        read_calibration_cases(source)
