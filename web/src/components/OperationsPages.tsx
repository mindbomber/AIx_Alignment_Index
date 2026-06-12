import { useEffect, useMemo, useState } from 'react'
import { ApiClient } from '../api'
import type {
  AssessmentComparison,
  AssessmentRecord,
  AuditRecord,
  JobRecord,
  PolicyRecord,
  RubricRecord,
  SystemRecord,
} from '../types'

type Page = 'Systems' | 'Rubrics' | 'Policies' | 'Audit' | 'Compare' | 'Reports'

type Props = {
  page: Page
  client: ApiClient
  systems: SystemRecord[]
  assessments: AssessmentRecord[]
  onSystemCreated: (system: SystemRecord) => void
}

function JsonEditor({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label>
      {label}
      <textarea
        rows={8}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        spellCheck={false}
      />
    </label>
  )
}

function downloadJob(job: JobRecord) {
  const content = job.result_json?.content
  if (!content) return
  const url = URL.createObjectURL(new Blob([content], { type: 'text/plain' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `aix-report-${job.id}.${job.result_json?.format === 'markdown' ? 'md' : job.result_json?.format ?? 'txt'}`
  anchor.click()
  URL.revokeObjectURL(url)
}

export function OperationsPages({
  page,
  client,
  systems,
  assessments,
  onSystemCreated,
}: Props) {
  const [rubrics, setRubrics] = useState<RubricRecord[]>([])
  const [policies, setPolicies] = useState<PolicyRecord[]>([])
  const [audit, setAudit] = useState<AuditRecord[]>([])
  const [jobs, setJobs] = useState<JobRecord[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [name, setName] = useState('')
  const [kind, setKind] = useState('ai_system')
  const [description, setDescription] = useState('')
  const [version, setVersion] = useState('1.0.0')
  const [jsonValue, setJsonValue] = useState('{}')
  const [baselineId, setBaselineId] = useState('')
  const [candidateId, setCandidateId] = useState('')
  const [comparison, setComparison] = useState<AssessmentComparison | null>(null)

  useEffect(() => {
    const loader =
      page === 'Rubrics'
        ? client.rubrics().then(setRubrics)
        : page === 'Policies'
          ? client.policies().then(setPolicies)
          : page === 'Audit'
            ? client.auditEvents().then(setAudit)
            : page === 'Reports'
              ? client.jobs().then(setJobs)
              : Promise.resolve()
    loader.catch((reason) =>
      setError(reason instanceof Error ? reason.message : `Could not load ${page}`),
    )
  }, [client, page])

  const finalized = useMemo(
    () => assessments.filter((assessment) => assessment.status === 'finalized'),
    [assessments],
  )

  async function act(operation: () => Promise<void>) {
    setError('')
    setMessage('')
    try {
      await operation()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Operation failed')
    }
  }

  return (
    <section className="operations-page">
      <header>
        <div>
          <h1>{page}</h1>
          <p>Organization-level AIx measurement operations and records.</p>
        </div>
      </header>
      {(message || error) && (
        <div className={error ? 'notice error' : 'notice'} role="status">
          {error || message}
        </div>
      )}
      {page === 'Systems' ? (
        <div className="resource-layout">
          <div className="resource-list">
            {systems.map((system) => (
              <article key={system.id}>
                <span>{system.kind}</span>
                <h2>{system.name}</h2>
                <p>{system.description || 'No description recorded.'}</p>
                <small>
                  {assessments.filter((item) => item.system_id === system.id).length}{' '}
                  assessments
                </small>
              </article>
            ))}
          </div>
          <aside className="resource-form">
            <h2>Register system</h2>
            <label>Name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label>Kind<input value={kind} onChange={(e) => setKind(e.target.value)} /></label>
            <label>Description<textarea value={description} onChange={(e) => setDescription(e.target.value)} /></label>
            <button className="primary" disabled={!name} onClick={() => act(async () => {
              const created = await client.createSystem({ name, kind, description })
              onSystemCreated(created)
              setName('')
              setDescription('')
              setMessage('System registered')
            })}>Register system</button>
          </aside>
        </div>
      ) : null}
      {page === 'Rubrics' ? (
        <div className="resource-layout">
          <div className="resource-list">
            {rubrics.map((rubric) => (
              <article key={rubric.id}>
                <span>{rubric.status}</span><h2>{rubric.slug}</h2>
                <p>Version {rubric.version}</p><code>{rubric.content_sha256.slice(0, 16)}</code>
                {rubric.status === 'draft' ? <button className="secondary" onClick={() => act(async () => {
                  const published = await client.publishRubric(rubric.id)
                  setRubrics((items) => items.map((item) => item.id === published.id ? published : item))
                  setMessage('Rubric published')
                })}>Publish</button> : null}
              </article>
            ))}
          </div>
          <aside className="resource-form">
            <h2>Create rubric version</h2>
            <label>Slug<input value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label>Version<input value={version} onChange={(e) => setVersion(e.target.value)} /></label>
            <JsonEditor label="Rubric JSON" value={jsonValue} onChange={setJsonValue} />
            <button className="primary" disabled={!name} onClick={() => act(async () => {
              const created = await client.createRubric({ slug: name, version, content: JSON.parse(jsonValue) })
              setRubrics((items) => [created, ...items])
              setMessage('Rubric version created')
            })}>Create rubric</button>
          </aside>
        </div>
      ) : null}
      {page === 'Policies' ? (
        <div className="resource-layout">
          <div className="resource-list">
            {policies.map((policy) => (
              <article key={policy.id}>
                <span>{policy.active ? 'active' : 'inactive'}</span>
                <h2>{policy.name}</h2>
                <pre>{JSON.stringify(policy.rules_json, null, 2)}</pre>
              </article>
            ))}
          </div>
          <aside className="resource-form">
            <h2>Create release policy</h2>
            <label>Name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
            <JsonEditor label="Rules JSON" value={jsonValue} onChange={setJsonValue} />
            <button className="primary" disabled={!name} onClick={() => act(async () => {
              const created = await client.createPolicy({ name, rules: JSON.parse(jsonValue), active: true })
              setPolicies((items) => [created, ...items])
              setMessage('Policy created')
            })}>Create policy</button>
          </aside>
        </div>
      ) : null}
      {page === 'Audit' ? (
        <div className="audit-table">
          {audit.map((event) => (
            <article key={event.id}>
              <time>{new Date(event.created_at).toLocaleString()}</time>
              <strong>{event.action}</strong>
              <span>{event.entity_type} · {event.entity_id}</span>
              <code>{event.event_hash.slice(0, 18)}</code>
            </article>
          ))}
        </div>
      ) : null}
      {page === 'Compare' ? (
        <div className="comparison-workbench">
          <label>Baseline<select value={baselineId} onChange={(e) => setBaselineId(e.target.value)}>
            <option value="">Choose assessment</option>
            {finalized.map((item) => <option key={item.id} value={item.id}>{systems.find((s) => s.id === item.system_id)?.name} · v{item.version}</option>)}
          </select></label>
          <label>Candidate<select value={candidateId} onChange={(e) => setCandidateId(e.target.value)}>
            <option value="">Choose assessment</option>
            {finalized.map((item) => <option key={item.id} value={item.id}>{systems.find((s) => s.id === item.system_id)?.name} · v{item.version}</option>)}
          </select></label>
          <button className="primary" disabled={!baselineId || !candidateId} onClick={() => act(async () => setComparison(await client.compare(baselineId, candidateId)))}>Compare results</button>
          {comparison ? <div className="delta-grid">
            <div><span>Adjusted score</span><strong>{comparison.adjusted_score_delta.toFixed(1)}</strong></div>
            <div><span>Confidence</span><strong>{comparison.confidence_delta.toFixed(2)}</strong></div>
            <div><span>Evidence quality</span><strong>{comparison.evidence_quality_delta.toFixed(2)}</strong></div>
            <div><span>Constraint skew</span><strong>{comparison.constraint_skew_delta.toFixed(1)}</strong></div>
            {Object.entries(comparison.domain_score_deltas).map(([domain, delta]) => <div key={domain}><span>{domain}</span><strong>{delta.toFixed(1)}</strong></div>)}
          </div> : null}
        </div>
      ) : null}
      {page === 'Reports' ? (
        <div className="resource-list reports-list">
          {jobs.filter((job) => job.kind === 'assessment_report').map((job) => (
            <article key={job.id}>
              <span>{job.status}</span><h2>Assessment report</h2>
              <p>{String(job.payload_json.assessment_id ?? '')}</p>
              <small>{new Date(job.created_at).toLocaleString()} · {job.attempts} attempts</small>
              {job.status === 'succeeded' ? <button className="secondary" onClick={() => downloadJob(job)}>Download</button> : null}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}
