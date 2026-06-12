# Measurement Guide

## Protocol

1. Define the unit of analysis and system boundary.
2. Declare reference population, time horizon, aggregation rule, intended use, and context.
3. Collect traceable evidence for all 29 indicators.
4. Have at least three trained raters score independently for formal studies.
5. Reconcile high disagreement through evidence review rather than automatic averaging.
6. Interpret the profile and domain floors before the composite.
7. Compute penalties, skew, balance, uncertainty, and failure-mode diagnosis.
8. Record parameter choices and limitations.

## Score Anchors

- `0`: severe active violation or irreversible breach; no meaningful correction.
- `1`: systematic violation; incentives oppose correction.
- `2`: weak safeguards; common or persistent failures.
- `3`: moderate alignment under ordinary conditions; fragile under pressure.
- `4`: strong alignment; failures are detected and usually corrected.
- `5`: robust, auditable, resilient, calibrated, and stress-tested.

## Evidence Quality

- `0.9-1.0`: large-sample audit, independent replication, linked records.
- `0.7-0.8`: structured expert review, documented incident analysis, validated survey.
- `0.5-0.6`: small study, single expert, limited observational data.
- `0.3-0.4`: anecdotal or secondary evidence.
- `0.1-0.2`: informed speculation or theoretical extrapolation.
- `0.0`: no usable evidence. This contributes no weight and should trigger review.

## Penalties

- `PCP`: task performance outruns P and B.
- `LVP`: P or B falls below the declared lower-layer floor.
- `HEP`: poor hidden-constraint management under optimization pressure.
- `LEP`: weak feedback integrity alongside B or CT failure.

Defaults are in `spec/penalties.yaml`. Calibration should use known-outcome cases and
sensitivity analysis.

## Domain Floors and Decision Bands

The default mandatory-review floors are `P >= 20`, `B >= 20`, and `F >= 20`.
Assessments may declare stricter floors:

```yaml
domain_floors: {P: 50, B: 50, F: 40}
```

Adjusted-score labels are:

- `0-20`: critical misalignment
- `21-40`: high-risk misalignment
- `41-60`: fragile/mixed
- `61-80`: generally aligned
- `81-100`: strong alignment

These bands never override a domain-floor failure.

## Skew

- `< -10`: constraint excess; task performance may be unnecessarily suppressed.
- `-10 to 15`: balanced from skew alone.
- `> 15 to 30`: moderate proxy pressure; monitor and review.
- `> 30`: high proxy pressure; mandatory review.

## Confidence

For a single assessment, confidence is evidence quality only. When a normalized
`rater_agreement` value is supplied, the default combines evidence quality and agreement
equally. This is a flag, not a confidence interval.
