# Contributing

AIx Open welcomes narrowly scoped improvements to scoring, validation, rubrics,
documentation, reliability analysis, and empirical validation.

## Development

```bash
python -m pip install -e ".[dev,charts]"
pytest --cov=aix --cov-report=term-missing
```

Changes to formulas, default parameters, indicator definitions, or interpretation
thresholds must:

1. Cite the paper section or empirical evidence motivating the change.
2. Add or update tests.
3. Preserve parameter disclosure and backwards compatibility where practical.
4. Distinguish measured findings from illustrative or proposed values.

New domain rubrics should retain the canonical indicator codes unless the proposal
explicitly introduces a versioned instrument.

