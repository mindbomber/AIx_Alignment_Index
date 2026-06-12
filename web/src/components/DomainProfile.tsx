import { domainNames, domainOrder, indicators } from '../data'
import type { AssessmentDocument, DomainCode } from '../types'

function domainScore(document: AssessmentDocument, domain: DomainCode) {
  const entries = indicators[domain].map(({ code }) => document.scores[code])
  const quality = entries.reduce(
    (total, entry) => total + (entry?.evidence_quality ?? 0),
    0,
  )
  if (!quality) return 0
  return (
    (entries.reduce(
      (total, entry) =>
        total + (entry?.score ?? 0) * (entry?.evidence_quality ?? 0),
      0,
    ) /
      (5 * quality)) *
    100
  )
}

function calculateProfile(document: AssessmentDocument) {
  return Object.fromEntries(
    domainOrder.map((domain) => [domain, domainScore(document, domain)]),
  ) as Record<DomainCode, number>
}

export function DomainProfile({
  document,
  finalized,
}: {
  document: AssessmentDocument
  finalized?: Record<DomainCode, number>
}) {
  const scores = finalized ?? calculateProfile(document)
  return (
    <section className="domain-profile" aria-label="Five-domain alignment profile">
      {domainOrder.map((domain) => (
        <div className="domain-column" key={domain}>
          <div className="domain-label">
            <strong>{domain}</strong>
            <span>{domainNames[domain]}</span>
          </div>
          <div className="domain-track">
            <span style={{ width: `${scores[domain]}%` }} />
          </div>
          <output>{scores[domain].toFixed(1)}</output>
        </div>
      ))}
    </section>
  )
}
