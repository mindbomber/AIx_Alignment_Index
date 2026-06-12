from pathlib import Path

import pytest

from aix.io import load_document


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def example_assessment():
    return load_document(ROOT / "examples" / "ai_output_assessment.yaml")

