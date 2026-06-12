# Rubric Authoring

AIx separates the canonical instrument from contextual interpretation.

- `spec/indicators.yaml` defines the 29 stable indicator codes, names, questions, and
  evidence examples.
- `spec/scoring_scale.yaml` defines the common six-level scale and evidence-quality
  guidance.
- `rubrics/*.yaml` define contextual notes and documented behavioral-anchor overrides.

The CLI resolves these layers:

```bash
aix rubric show ai_systems
```

The resulting YAML contains every canonical indicator, the common scale, and any
contextual overrides. This avoids copying 29 definitions into every domain file and
prevents silent divergence.

## Adding a Rubric

Create `rubrics/<name>.yaml`:

```yaml
name: AIx Example Domain Rubric
version: 0.1.0
extends: core
context_notes:
  P: Describe domain-specific factual and material evidence.
  B: Describe affected populations and human-impact evidence.
anchors:
  P1:
    name: Factual/material realism
    5: A documented, domain-specific behavioral anchor.
```

Only introduce numeric thresholds when supported by published evidence or a declared
calibration study. General anchors remain the default otherwise.

## Versioning

Changes to indicator meaning, score anchors, or penalty calibration alter the instrument
and require a version change, migration notes, tests, and a validity rationale.

