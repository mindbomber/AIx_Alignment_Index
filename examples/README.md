# Examples

- `ai_output_assessment.yaml`: consequential advisory assistant.
- `platform_assessment.yaml`: proxy-heavy digital platform.
- `institution_assessment.yaml`: public-service intake process.
- `paper_worked_example.yaml`: exact Section 15 score and evidence-weight fixture.
- `multi_rater_scores.csv`: reliability command input.

Generate artifacts:

```bash
aix report examples/ai_output_assessment.yaml --out examples/reports/ai_output.md
aix report examples/platform_assessment.yaml --format json --out examples/reports/platform.json
aix chart examples/ai_output_assessment.yaml --out-dir examples/charts
aix reliability examples/multi_rater_scores.csv
```
