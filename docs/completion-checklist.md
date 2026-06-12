# MVP Completion Checklist

This checklist maps the Expanded Edition, the engineering scope, and the reference
`aix-open-v0.1` scaffold to inspectable repository evidence.

## Repository and Packaging

- [x] Python package under `src/aix`
- [x] `README`, license, contribution guide, code of conduct
- [x] Editable install and `aix` console command
- [x] Wheel and source distribution build
- [x] GitHub Actions test matrix
- [x] Release archive command and generated v0.1 artifacts

## Measurement

- [x] Five canonical domains and 29 indicators
- [x] Evidence-quality weighted domain scores
- [x] Declared weights and arithmetic/geometric composites
- [x] PCP, LVP, HEP, and LEP with configurable disclosed parameters
- [x] Constraint skew, balance range, and weighted profile distance
- [x] Domain floors and mandatory-review gate
- [x] Adjusted-score interpretation bands
- [x] Failure-mode diagnosis and recommendations
- [x] ATS proxy dynamics estimate with explicit caveat
- [x] Domain and overall confidence from evidence quality and optional rater agreement

## Instrument Specification

- [x] JSON Schema plus runtime semantic validation
- [x] Canonical scoring-scale specification
- [x] Canonical indicator specification with questions, anchors, and evidence examples
- [x] Core and domain-context rubric files
- [x] Rubric inheritance resolved by the CLI

## Reliability

- [x] Mean, standard deviation, mean absolute disagreement, and agreement within one
- [x] Pairwise quadratic weighted kappa
- [x] ICC(2,1) for complete rater panels
- [x] Per-indicator disagreement and confidence diagnostics
- [x] Reliability JSON and Markdown reports

## Reports and CLI

- [x] Validate, score, report, compare, rubric list/show
- [x] Batch scoring and reliability analysis
- [x] Markdown, JSON, CSV, and HTML reports
- [x] Machine-readable comparison output
- [x] Nonzero exit behavior for invalid input

## Visuals and Examples

- [x] Domain bar, radar, and penalty charts
- [x] Skew comparison and before/after comparison charts
- [x] PNG and SVG output
- [x] AI, platform, and institution assessments
- [x] Generated reports and visuals for every assessment
- [x] Executable notebook demonstration

## Documentation and Scientific Boundaries

- [x] ATS/AIx/AANA relationship
- [x] Scoring, penalties, assessment creation, interpretation, and rubric authoring
- [x] Reliability workflow and validation roadmap
- [x] Cross-domain use cases
- [x] Limitations, anti-Goodhart guidance, and parameter transparency
- [x] Explicit research-alpha and non-certification warnings

