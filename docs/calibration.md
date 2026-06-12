# Calibration And Criterion Validation

AIx calibration links assessment results to independently observed criteria.
The input CSV records an assessment path, a train/validation partition, a
binary incident outcome, and an external expert score.

```bash
aix calibrate DATASET.csv --format json
aix calibrate DATASET.csv --format markdown --out calibration-report.md
```

The command:

1. validates case identifiers, paths, outcomes, scores, and split integrity;
2. searches a disclosed scale over the four penalty coefficients;
3. selects an incident decision threshold using training cases only;
4. reports holdout MAE, Pearson correlation, ROC AUC, Brier score,
   sensitivity, and specificity;
5. fingerprints the source dataset and emits calibrated parameters.

The bundled development benchmark proves reproducibility of the engineering
pipeline. It does not establish empirical validity. A publishable study should
pre-register the sampling frame and hypotheses, use independent trained raters,
preserve an untouched holdout set, document missingness and exclusions, report
subgroup performance, and publish de-identified case provenance where lawful.
