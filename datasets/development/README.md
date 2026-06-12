# AIx Development Calibration Benchmark

This dataset exercises the calibration and criterion-validation pipeline using
the repository's worked and illustrative assessments. It is deterministic test
data, not an independently sampled empirical validation study.

The labels represent scenario interpretations for software development:

- `observed_incident`: binary adverse-outcome label;
- `expert_score`: external criterion score on a 0-100 scale;
- `split`: calibration or untouched validation partition.

Run:

```bash
aix calibrate datasets/development/criterion_cases.csv \
  --format markdown \
  --out reports/development_calibration.md
```

Replace this benchmark with preregistered, independently rated cases for any
scientific, regulatory, or consequential validity claim.
