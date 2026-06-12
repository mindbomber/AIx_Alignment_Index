# Validation Roadmap

AIx includes a reproducible calibration and criterion-validation pipeline, but
the bundled development benchmark is not an independent empirical validation.
External data collection and replication remain required for validity claims.

## Phase 1: Content and Anchor Refinement

Convene cross-domain expert panels, test indicator coverage, refine behavioral anchors,
and document domain adaptations.

## Phase 2: Reliability

Use at least three trained raters. Estimate weighted kappa, ICC, disagreement, and
generalizability across raters, indicators, domains, and occasions.

Paper targets:

| Context | Minimum weighted kappa | Target ICC |
|---|---:|---:|
| Research/exploratory | 0.41 | 0.70 |
| Audit/monitoring | 0.61 | 0.80 |
| Regulatory/high-stakes | 0.81 | 0.90 |

## Phase 3: Construct and Criterion Validity

Test factor structure, convergent and discriminant behavior, known-outcome cases, and
whether domain profiles distinguish substantively different failure modes.

## Phase 4: Predictive and Intervention Validity

Test whether AIx predicts incidents and whether interventions that improve scores reduce
real failures. Calibrate penalty parameters using held-out cases.

## Phase 5: Governance

Version rubrics, publish calibration datasets, rotate indicators where gaming emerges,
and require independent audits for consequential use.
