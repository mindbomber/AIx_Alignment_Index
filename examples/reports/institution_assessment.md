# AIx Report: Illustrative Public Service Institution

## Executive Summary

- Adjusted AIx: **63.65 / 100**
- Raw arithmetic AIx: **63.65**
- Raw geometric AIx: **63.51**
- Constraint skew: **-2.59** (balanced)
- Confidence: **0.696** (evidence_quality_only_single_assessment)
- Decision band: **generally_aligned**
- Mandatory review: **no**

AIx is interpreted vector-first: domain scores, evidence, and hard lower-layer concerns take priority over the composite.

## System Metadata

- **Name:** Illustrative Public Service Institution
- **Type:** institution
- **Unit Of Analysis:** benefits intake process
- **Reference Population:** applicants and staff
- **Time Horizon:** one year
- **Aggregation Rule:** equal domain weighting
- **Intended Use:** demonstration only

## Domain Profile

| Domain | Score | Evidence quality | Weight |
|---|---:|---:|---:|
| P - Physical/Factual Alignment | 67.62 | 0.700 | 0.200 |
| B - Biological/Human-Impact Alignment | 62.86 | 0.700 | 0.200 |
| CT - Constructed/Task Alignment | 63.48 | 0.767 | 0.200 |
| H - Hidden-Constraint Management | 56.55 | 0.580 | 0.200 |
| F - Feedback Integrity | 67.73 | 0.733 | 0.200 |

### Domain Confidence

- **P:** 0.700
- **B:** 0.700
- **CT:** 0.767
- **H:** 0.580
- **F:** 0.733

**Balance range:** 11.18 (well_balanced)

## Penalty Breakdown

| Penalty | Deduction |
|---|---:|
| PCP | 0.00 |
| LVP | 0.00 |
| HEP | 0.00 |
| LEP | 0.00 |

**Total penalty:** 0.00
**Optimization pressure:** 0.000 (estimated_from_positive_constraint_skew)
**Decision interpretation:** Ordinary use still requires periodic stress testing and audit.

## Failure-Mode Diagnosis

- `no_primary_failure_mode_detected`

## Recommendations

- Maintain monitoring and interpret indicator evidence before the composite.

## Parameter Disclosure

| Parameter | Value |
|---|---:|
| `eta_p` | 0.5 |
| `theta_p` | 15 |
| `eta_l` | 0.6 |
| `theta_l` | 40 |
| `eta_h` | 0.4 |
| `theta_h` | 50 |
| `pi0` | 0.3 |
| `pi_max` | 1 |
| `eta_e` | 0.5 |
| `theta_e` | 50 |
| `theta_b` | 40 |
| `theta_c` | 35 |

## ATS Dynamics Bridge

**Directional estimate:** 0.6

Directional ATS bridge only; this is not a measured alignment rate.

## Limitations

- AIx is a structured measurement proposal, not a validated regulatory instrument.
- Ordinal indicator scores and composite decimals must not be treated as false precision.
- The profile, evidence, disagreement, and domain floors take priority over the scalar score.
