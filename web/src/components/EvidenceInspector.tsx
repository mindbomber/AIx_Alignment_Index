import { useState } from 'react'
import type { EvidenceRecord, ScoreEntry } from '../types'

type Props = {
  code: string
  entry: ScoreEntry
  evidence: EvidenceRecord[]
  disabled: boolean
  onNotesChange: (notes: string) => void
  onAddEvidence: (payload: {
    indicator_code: string
    source_type: string
    uri: string
    content_sha256: string
    trust_score: number
    classification: string
  }) => Promise<void>
  onUploadEvidence: (payload: {
    indicator_code: string
    source_type: string
    trust_score: number
    classification: string
    file: File
  }) => Promise<void>
}

export function EvidenceInspector({
  code,
  entry,
  evidence,
  disabled,
  onNotesChange,
  onAddEvidence,
  onUploadEvidence,
}: Props) {
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')
  const [entryMode, setEntryMode] = useState<'file' | 'link'>('file')
  const matching = evidence.filter((item) => item.indicator_code === code)

  async function add(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    const form = new FormData(event.currentTarget)
    try {
      const common = {
        indicator_code: code,
        source_type: String(form.get('source_type')),
        trust_score: Number(form.get('trust_score')),
        classification: String(form.get('classification')),
      }
      if (entryMode === 'file') {
        const file = form.get('file')
        if (!(file instanceof File) || !file.size) {
          throw new Error('Choose an evidence file')
        }
        await onUploadEvidence({ ...common, file })
      } else {
        await onAddEvidence({
          ...common,
          uri: String(form.get('uri')),
          content_sha256: String(form.get('content_sha256')),
        })
      }
      setShowForm(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not add evidence')
    }
  }

  return (
    <aside className="inspector">
      <header>
        <div>
          <span>Selected indicator</span>
          <h2>{code}</h2>
        </div>
        <span className="evidence-count">{matching.length} sources</span>
      </header>
      <label className="notes-field">
        Assessment notes
        <textarea
          value={entry.notes ?? ''}
          disabled={disabled}
          onChange={(event) => onNotesChange(event.target.value)}
          placeholder="Explain the score and cite the strongest evidence."
        />
      </label>
      <div className="inspector-section-title">
        <h3>Evidence provenance</h3>
        <button
          type="button"
          className="text-button"
          disabled={disabled}
          onClick={() => setShowForm((value) => !value)}
        >
          {showForm ? 'Cancel' : 'Add evidence'}
        </button>
      </div>
      {showForm ? (
        <form className="evidence-form" onSubmit={add}>
          <div className="dialog-tabs compact">
            <button
              type="button"
              className={entryMode === 'file' ? 'active' : ''}
              onClick={() => setEntryMode('file')}
            >
              Upload
            </button>
            <button
              type="button"
              className={entryMode === 'link' ? 'active' : ''}
              onClick={() => setEntryMode('link')}
            >
              External link
            </button>
          </div>
          <label>
            Source type
            <select name="source_type" defaultValue="audit">
              <option>audit</option>
              <option>expert_review</option>
              <option>incident_report</option>
              <option>system_log</option>
              <option>study</option>
            </select>
          </label>
          {entryMode === 'file' ? (
            <label>
              Evidence file
              <input name="file" type="file" required />
            </label>
          ) : (
            <>
              <label>
                URI
                <input name="uri" type="url" required />
              </label>
              <label>
                SHA-256
                <input name="content_sha256" pattern="[a-fA-F0-9]{64}" required />
              </label>
            </>
          )}
          <div className="form-pair">
            <label>
              Trust
              <input
                name="trust_score"
                type="number"
                min="0"
                max="1"
                step="0.05"
                defaultValue="0.8"
              />
            </label>
            <label>
              Classification
              <select name="classification" defaultValue="internal">
                <option>public</option>
                <option>internal</option>
                <option>confidential</option>
                <option>restricted</option>
              </select>
            </label>
          </div>
          {error ? <div className="form-error">{error}</div> : null}
          <button className="primary">Record evidence</button>
        </form>
      ) : null}
      <div className="evidence-list">
        {matching.length ? (
          matching.map((item) => (
            <article key={item.id}>
              <div>
                <strong>{item.source_type.replaceAll('_', ' ')}</strong>
                <span>{item.classification}</span>
              </div>
              <a href={item.uri} target="_blank" rel="noreferrer">
                {item.uri}
              </a>
              <dl>
                <div>
                  <dt>Trust</dt>
                  <dd>{item.trust_score.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>Integrity</dt>
                  <dd>{item.content_sha256.slice(0, 10)}…</dd>
                </div>
              </dl>
            </article>
          ))
        ) : (
          <div className="empty-evidence">
            No structured evidence is attached to {code}.
          </div>
        )}
      </div>
    </aside>
  )
}
