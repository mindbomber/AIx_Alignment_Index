# Reliability Analysis

Input CSV:

```csv
rater_id,system_id,indicator,score
r1,system_a,P1,4
r2,system_a,P1,3
r3,system_a,P1,4
```

Run:

```bash
aix reliability ratings.csv --format markdown
```

Outputs include:

- mean and population standard deviation
- mean absolute pairwise disagreement
- agreement within one point
- mean pairwise quadratic weighted kappa
- ICC(2,1) when a complete panel has at least two items and two raters
- Cronbach alpha across complete indicator panels
- domain-level disagreement and confidence summaries
- per-system/indicator confidence based on the paper's equal weighting of evidence and
  agreement; reliability CSV lacks evidence quality, so its displayed group confidence
  uses neutral evidence quality `0.5`

Kappa and ICC should be interpreted with sample size, prevalence, rater training, and
missingness. They do not establish construct or predictive validity.
