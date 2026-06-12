# AIx Open

**AIx is an open-source framework for measuring alignment across factual, human-impact,
task, hidden-risk, and feedback dimensions.**

AIx Open implements the measurement proposal in *The Alignment Index (AIx) as a
Standalone Measurement Pillar: Expanded Edition* (Sori, 2026). It produces a
five-domain profile, arithmetic and geometric composites, explicit penalties,
constraint-skew diagnostics, evidence-quality metadata, comparisons, reports, charts,
and basic multi-rater reliability statistics.

> Project status: research alpha. AIx is not yet a validated psychometric, regulatory,
> certification, or safety instrument.

## Domains

| Code | Domain | Core question |
|---|---|---|
| P | Physical/Factual Alignment | Does the system respect facts and material constraints? |
| B | Biological/Human-Impact Alignment | Does it preserve safety, dignity, agency, and wellbeing? |
| CT | Constructed/Task Alignment | Does it satisfy legitimate task constraints without outrunning deeper layers? |
| H | Hidden-Constraint Management | Does it map unknowns, shifts, dependencies, and tail risks? |
| F | Feedback Integrity | Can outcomes be observed, audited, calibrated, and corrected? |

## Quick Start

```bash
python -m pip install -e ".[dev,charts]"
aix validate examples/ai_output_assessment.yaml
aix score examples/ai_output_assessment.yaml
aix report examples/ai_output_assessment.yaml --format markdown
aix chart examples/ai_output_assessment.yaml --out-dir examples/charts
aix batch examples --out examples/reports/batch.json
pytest
```

## Core Formulas

For each domain, evidence-quality-weighted indicator scores are normalized to 0-100:

```text
D = sum(q_i * x_i) / (5 * sum(q_i)) * 100
```

The default arithmetic composite uses declared equal weights. The geometric variant
penalizes imbalance more strongly.

```text
AIx_adj = max(0, AIx_arith - PCP - LVP - HEP - LEP)
Skew = CT - ((P + B + F) / 3)
```

Penalty defaults are calibrated starting points from the Expanded Edition, not universal
constants. Every result discloses the parameters actually used.

## CLI

```text
aix validate ASSESSMENT [--allow-partial]
aix score ASSESSMENT [--format summary|markdown|json|csv|html]
aix report ASSESSMENT --format markdown|json|csv|html [--out PATH]
aix compare FIRST SECOND [--out PATH]
aix rubric list
aix rubric show core
aix reliability RATINGS.csv [--format json|markdown] [--out PATH]
aix chart ASSESSMENT [COMPARISON] [--format png|svg|both] [--out-dir DIR]
aix batch DIRECTORY [--out PATH]
aix export ASSESSMENT --format json|csv --out PATH
```

See the [measurement guide](docs/measurement-guide.md),
[rubric authoring guide](docs/rubric-authoring.md),
[reliability guide](docs/reliability.md),
[use cases](docs/use-cases.md),
[ATS dynamics bridge](docs/ats-dynamics-bridge.md), and
[validation roadmap](docs/validation-roadmap.md).

## ATS, AIx, and AANA

- ATS supplies the layered-constraint theory of why optimizing systems drift.
- AIx is the independent measurement instrument that diagnoses where drift appears.
- AANA is one verifier-grounded correction architecture that can consume AIx results.

AIx does not require AANA and must not imply that measurement alone corrects a system.

## Responsible Interpretation

1. Interpret the domain vector before the scalar.
2. Treat severe P or B weakness as an independent concern even when the composite is high.
3. Require traceable evidence for every indicator.
4. Report uncertainty and rater disagreement.
5. Do not interpret decimal differences as meaningful without validation data.
6. Monitor AIx itself for Goodhart pressure.

## License

MIT License. See [LICENSE](LICENSE).
