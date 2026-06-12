import { domainNames, domainOrder, indicators } from '../data'
import type { AssessmentDocument, ScoreEntry } from '../types'

type Props = {
  document: AssessmentDocument
  selected: string
  disabled: boolean
  onSelect: (code: string) => void
  onChange: (code: string, entry: ScoreEntry) => void
}

export function IndicatorTable({
  document,
  selected,
  disabled,
  onSelect,
  onChange,
}: Props) {
  return (
    <div className="indicator-table">
      <div className="table-header" aria-hidden="true">
        <span>Indicator</span>
        <span>Score</span>
        <span>Evidence quality</span>
        <span>Notes</span>
      </div>
      {domainOrder.map((domain) => (
        <section key={domain} className="domain-group">
          <h3>
            <span>{domain}</span>
            {domainNames[domain]}
          </h3>
          {indicators[domain].map((indicator) => {
            const entry = document.scores[indicator.code]
            return (
              <div
                className={`indicator-row ${selected === indicator.code ? 'selected' : ''}`}
                key={indicator.code}
                onClick={() => onSelect(indicator.code)}
              >
                <button
                  type="button"
                  className="indicator-name"
                  onClick={() => onSelect(indicator.code)}
                >
                  <strong>{indicator.code}</strong>
                  <span>{indicator.name}</span>
                </button>
                <label>
                  <span className="mobile-label">Score</span>
                  <select
                    aria-label={`${indicator.code} score`}
                    value={entry.score}
                    disabled={disabled}
                    onChange={(event) =>
                      onChange(indicator.code, {
                        ...entry,
                        score: Number(event.target.value),
                      })
                    }
                  >
                    {[0, 1, 2, 3, 4, 5].map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </select>
                </label>
                <label className="quality-control">
                  <span className="mobile-label">Evidence quality</span>
                  <input
                    aria-label={`${indicator.code} evidence quality`}
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={entry.evidence_quality}
                    disabled={disabled}
                    onChange={(event) =>
                      onChange(indicator.code, {
                        ...entry,
                        evidence_quality: Number(event.target.value),
                      })
                    }
                  />
                  <output>{entry.evidence_quality.toFixed(2)}</output>
                </label>
                <span className={entry.notes ? 'notes-ready' : 'notes-empty'}>
                  {entry.notes ? 'Documented' : 'Missing'}
                </span>
              </div>
            )
          })}
        </section>
      ))}
    </div>
  )
}
