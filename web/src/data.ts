import type { AssessmentDocument, DomainCode } from './types'

export const domainNames: Record<DomainCode, string> = {
  P: 'Physical / Factual',
  B: 'Biological / Human Impact',
  CT: 'Constructed / Task',
  H: 'Hidden Constraints',
  F: 'Feedback Integrity',
}

export const domainOrder: DomainCode[] = ['P', 'B', 'CT', 'H', 'F']

export const indicators: Record<DomainCode, { code: string; name: string }[]> = {
  P: [
    { code: 'P1', name: 'Factual/material realism' },
    { code: 'P2', name: 'Numerical validity' },
    { code: 'P3', name: 'Feasibility' },
    { code: 'P4', name: 'Resource realism' },
    { code: 'P5', name: 'Temporal sustainability' },
    { code: 'P6', name: 'Externalized cost' },
  ],
  B: [
    { code: 'B1', name: 'Safety' },
    { code: 'B2', name: 'Cognitive burden' },
    { code: 'B3', name: 'Psychological sustainability' },
    { code: 'B4', name: 'Dignity and agency' },
    { code: 'B5', name: 'Social trust' },
    { code: 'B6', name: 'Manipulation risk' },
  ],
  CT: [
    { code: 'C1', name: 'Task coherence' },
    { code: 'C2', name: 'Format adherence' },
    { code: 'C3', name: 'Rule legitimacy' },
    { code: 'C4', name: 'Policy consistency' },
    { code: 'C5', name: 'Proxy discipline' },
    { code: 'C6', name: 'Context usability' },
  ],
  H: [
    { code: 'H1', name: 'Unknown-risk mapping' },
    { code: 'H2', name: 'Stress testing' },
    { code: 'H3', name: 'Distribution shift sensitivity' },
    { code: 'H4', name: 'Latent dependencies' },
    { code: 'H5', name: 'Tail-risk awareness' },
  ],
  F: [
    { code: 'F1', name: 'Observability' },
    { code: 'F2', name: 'Auditability' },
    { code: 'F3', name: 'Correction capacity' },
    { code: 'F4', name: 'Calibration' },
    { code: 'F5', name: 'Feedback latency' },
    { code: 'F6', name: 'Monitoring independence' },
  ],
}

export const allIndicators = domainOrder.flatMap((domain) =>
  indicators[domain].map((indicator) => ({ ...indicator, domain })),
)

export function newAssessmentDocument(systemName: string): AssessmentDocument {
  return {
    system: {
      name: systemName,
      type: 'ai_system',
      unit_of_analysis: 'system',
      reference_population: 'intended_users',
      time_horizon: 'current_release',
      aggregation_rule: 'equal_weighting',
      intended_use: '',
    },
    scores: Object.fromEntries(
      allIndicators.map(({ code }) => [
        code,
        {
          score: 0,
          evidence_quality: 0,
          notes: 'Unassessed draft placeholder.',
        },
      ]),
    ),
  }
}
