import { startTransition, useEffect, useMemo, useState } from 'react'
import { ApiClient } from './api'
import { LoginScreen } from './components/LoginScreen'
import { DomainProfile } from './components/DomainProfile'
import { EvidenceInspector } from './components/EvidenceInspector'
import { IndicatorTable } from './components/IndicatorTable'
import { WorkflowTimeline } from './components/WorkflowTimeline'
import { CreateWorkspaceItem } from './components/CreateWorkspaceItem'
import { AdminIdentity } from './components/AdminIdentity'
import { OperationsPages } from './components/OperationsPages'
import { newAssessmentDocument } from './data'
import type {
  AssessmentComparison,
  AssessmentRecord,
  EvidenceRecord,
  Principal,
  ScoreEntry,
  SystemRecord,
} from './types'
import './App.css'

function App() {
  const [token, setToken] = useState(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1))
    const oidcToken = fragment.get('access_token')
    if (oidcToken) {
      sessionStorage.setItem('aix_token', oidcToken)
      window.history.replaceState({}, document.title, window.location.pathname)
      return oidcToken
    }
    return sessionStorage.getItem('aix_token') ?? ''
  })
  const [principal, setPrincipal] = useState<Principal | null>(null)
  const [systems, setSystems] = useState<SystemRecord[]>([])
  const [assessments, setAssessments] = useState<AssessmentRecord[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [selectedIndicator, setSelectedIndicator] = useState('P1')
  const [evidence, setEvidence] = useState<EvidenceRecord[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(Boolean(token))
  const [showCreate, setShowCreate] = useState(false)
  const [comparison, setComparison] = useState<AssessmentComparison | null>(null)
  const [compareId, setCompareId] = useState('')
  const [reportBusy, setReportBusy] = useState(false)
  const [activePage, setActivePage] = useState<
    | 'Assessments'
    | 'Systems'
    | 'Rubrics'
    | 'Policies'
    | 'Compare'
    | 'Reports'
    | 'Identity'
    | 'Audit'
  >('Assessments')

  const client = useMemo(() => (token ? new ApiClient(token) : null), [token])
  const selected = assessments.find((assessment) => assessment.id === selectedId)
  const system = systems.find((item) => item.id === selected?.system_id)
  const comparisonOptions = assessments.filter(
    (item) =>
      item.id !== selected?.id &&
      item.system_id === selected?.system_id &&
      item.status === 'finalized',
  )

  useEffect(() => {
    if (!client) return
    let cancelled = false
    Promise.all([client.me(), client.systems(), client.assessments()])
      .then(([me, loadedSystems, loadedAssessments]) => {
        if (cancelled) return
        setPrincipal(me)
        setSystems(loadedSystems)
        setAssessments(loadedAssessments)
        setSelectedId((current) => current || loadedAssessments[0]?.id || '')
      })
      .catch((reason) => {
        if (cancelled) return
        setError(reason instanceof Error ? reason.message : 'Could not load workspace')
        sessionStorage.removeItem('aix_token')
        setToken('')
      })
      .finally(() => setLoading(false))
    return () => {
      cancelled = true
    }
  }, [client])

  useEffect(() => {
    if (!client || !selectedId) return
    client
      .evidence(selectedId)
      .then(setEvidence)
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : 'Could not load evidence'),
      )
  }, [client, selectedId])

  function authenticated(value: string) {
    sessionStorage.setItem('aix_token', value)
    setLoading(true)
    setToken(value)
    setError('')
  }

  function updateScore(code: string, entry: ScoreEntry) {
    if (!selected) return
    setAssessments((current) =>
      current.map((assessment) =>
        assessment.id === selected.id
          ? {
              ...assessment,
              input_json: {
                ...assessment.input_json,
                scores: { ...assessment.input_json.scores, [code]: entry },
              },
            }
          : assessment,
      ),
    )
  }

  async function save() {
    if (!client || !selected) return
    setMessage('')
    setError('')
    try {
      const saved = await client.saveAssessment(selected.id, selected.input_json)
      setAssessments((current) =>
        current.map((item) => (item.id === saved.id ? saved : item)),
      )
      setMessage('Draft saved')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save draft')
    }
  }

  async function transition(
    action: 'submit' | 'approve' | 'reject' | 'finalize',
  ) {
    if (!client || !selected) return
    setMessage('')
    setError('')
    try {
      if (selected.status === 'draft') await save()
      const updated = await client.transition(selected.id, action)
      setAssessments((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setMessage(`Assessment ${updated.status.replace('_', ' ')}`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Workflow action failed')
    }
  }

  async function createSystem(payload: {
    name: string
    kind: string
    description: string
  }) {
    if (!client) throw new Error('Session is unavailable')
    const created = await client.createSystem(payload)
    setSystems((current) => [...current, created])
    return created
  }

  async function createAssessment(target: SystemRecord) {
    if (!client) throw new Error('Session is unavailable')
    const created = await client.createAssessment(
      target.id,
      newAssessmentDocument(target.name),
    )
    setAssessments((current) => [created, ...current])
    setSelectedId(created.id)
    setMessage('Assessment created')
  }

  async function compare() {
    if (!client || !selected || !compareId) return
    setError('')
    try {
      setComparison(await client.compare(compareId, selected.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Comparison failed')
    }
  }

  async function downloadReport() {
    if (!client || !selected) return
    setReportBusy(true)
    setError('')
    try {
      let job = await client.createReport(selected.id)
      for (let attempt = 0; attempt < 30 && !['succeeded', 'failed'].includes(job.status); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 500))
        job = await client.job(job.id)
      }
      if (job.status !== 'succeeded' || !job.result_json?.content) {
        throw new Error(job.error ?? 'Report generation timed out')
      }
      const url = URL.createObjectURL(
        new Blob([job.result_json.content], { type: 'text/markdown' }),
      )
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${selected.input_json.system.name.replaceAll(' ', '-')}-aix-report.md`
      anchor.click()
      URL.revokeObjectURL(url)
      setMessage('Report generated')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not generate report')
    } finally {
      setReportBusy(false)
    }
  }

  if (!token) return <LoginScreen onAuthenticated={authenticated} />
  if (loading) return <div className="loading-screen">Loading AIx workspace…</div>
  if (!principal) return <LoginScreen onAuthenticated={authenticated} />
  const baseNav = [
    'Assessments',
    'Systems',
    'Rubrics',
    'Policies',
    'Compare',
    'Reports',
  ] as const
  const navItems =
    principal.role === 'owner' || principal.role === 'admin'
      ? ([...baseNav, 'Identity', 'Audit'] as const)
      : baseNav

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="wordmark">AIx</div>
        <nav aria-label="Primary navigation">
          {navItems.map((item) => (
            <button
              className={item === activePage ? 'active' : ''}
              key={item}
              type="button"
              onClick={() => setActivePage(item)}
            >
              <span aria-hidden="true">{item.slice(0, 1)}</span>
              {item}
            </button>
          ))}
        </nav>
        <button
          className="sign-out"
          onClick={() => {
            sessionStorage.removeItem('aix_token')
            setToken('')
          }}
        >
          Sign out
        </button>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div>
            <strong>{principal.organization.name}</strong>
            <span>Measurement workspace</span>
          </div>
          <div className="account">
            <button className="secondary create-button" onClick={() => setShowCreate(true)}>
              New
            </button>
            <span>{principal.display_name.slice(0, 1).toUpperCase()}</span>
            <div>
              <strong>{principal.display_name}</strong>
              <small>{principal.role}</small>
            </div>
          </div>
        </header>
        {activePage === 'Identity' ? (
          <AdminIdentity
            client={client!}
            principal={principal}
            onOrganizationChange={(organization) =>
              setPrincipal((current) =>
                current ? { ...current, organization } : current,
              )
            }
          />
        ) : activePage !== 'Assessments' ? (
          <OperationsPages
            page={activePage}
            client={client!}
            systems={systems}
            assessments={assessments}
            onSystemCreated={(created) =>
              setSystems((current) => [...current, created])
            }
          />
        ) : selected ? (
          <>
            <section className="assessment-header">
              <div className="assessment-title">
                <div>
                  <button type="button" className="back-button" aria-label="Back">
                    ←
                  </button>
                  <div>
                    <h1>{system?.name ?? selected.input_json.system.name}</h1>
                    <p>
                      Assessment version {selected.version}
                      <span className={`status ${selected.status}`}>
                        {selected.status.replace('_', ' ')}
                      </span>
                    </p>
                  </div>
                </div>
                <div className="header-actions">
                  {selected.status === 'draft' ? (
                    <>
                      <button className="secondary" onClick={save}>
                        Save draft
                      </button>
                      <button className="primary" onClick={() => transition('submit')}>
                        Submit for review
                      </button>
                    </>
                  ) : null}
                  {selected.status === 'in_review' ? (
                    <>
                      <button className="secondary" onClick={() => transition('reject')}>
                        Return to draft
                      </button>
                      <button className="primary" onClick={() => transition('approve')}>
                        Approve assessment
                      </button>
                    </>
                  ) : null}
                  {selected.status === 'approved' ? (
                    <button className="primary" onClick={() => transition('finalize')}>
                      Finalize result
                    </button>
                  ) : null}
                  {selected.status === 'finalized' ? (
                    <button className="primary" disabled={reportBusy} onClick={downloadReport}>
                      {reportBusy ? 'Generating…' : 'Download report'}
                    </button>
                  ) : null}
                </div>
              </div>
              <DomainProfile
                document={selected.input_json}
                finalized={selected.result_json?.domain_scores}
              />
              <div className="summary-strip">
                <div>
                  <span>Adjusted score</span>
                  <strong>{selected.result_json?.adjusted_score.toFixed(1) ?? 'Pending'}</strong>
                </div>
                <div>
                  <span>Confidence</span>
                  <strong>{selected.result_json?.confidence.toFixed(2) ?? 'Pending'}</strong>
                </div>
                <div>
                  <span>Evidence quality</span>
                  <strong>
                    {selected.result_json?.evidence_quality.toFixed(2) ?? 'Draft'}
                  </strong>
                </div>
                <div>
                  <span>Constraint skew</span>
                  <strong>
                    {selected.result_json?.constraint_skew.toFixed(1) ?? 'Pending'}
                  </strong>
                </div>
              </div>
            </section>
            {(message || error) && (
              <div className={error ? 'notice error' : 'notice'} role="status">
                {error || message}
              </div>
            )}
            <div className="assessment-layout">
              <section className="score-workspace">
                <div className="section-heading">
                  <div>
                    <h2>Indicator scoring</h2>
                    <p>Score each indicator against traceable evidence.</p>
                  </div>
                  <select
                    aria-label="Choose assessment"
                    value={selectedId}
                    onChange={(event) =>
                      startTransition(() => setSelectedId(event.target.value))
                    }
                  >
                    {assessments.map((item) => (
                      <option key={item.id} value={item.id}>
                        {systems.find((value) => value.id === item.system_id)?.name ??
                          item.input_json.system.name}{' '}
                        · v{item.version}
                      </option>
                    ))}
                  </select>
                </div>
                <IndicatorTable
                  document={selected.input_json}
                  selected={selectedIndicator}
                  disabled={selected.status !== 'draft'}
                  onSelect={setSelectedIndicator}
                  onChange={updateScore}
                />
              </section>
              <EvidenceInspector
                code={selectedIndicator}
                entry={selected.input_json.scores[selectedIndicator]}
                evidence={evidence}
                disabled={selected.status === 'finalized'}
                onNotesChange={(notes) =>
                  updateScore(selectedIndicator, {
                    ...selected.input_json.scores[selectedIndicator],
                    notes,
                  })
                }
                onAddEvidence={async (payload) => {
                  if (!client) return
                  const created = await client.addEvidence(selected.id, payload)
                  setEvidence((current) => [...current, created])
                }}
                onUploadEvidence={async (payload) => {
                  if (!client) return
                  const created = await client.uploadEvidence(selected.id, payload)
                  setEvidence((current) => [...current, created])
                }}
              />
            </div>
            {selected.status === 'finalized' && comparisonOptions.length ? (
              <section className="comparison-panel">
                <div>
                  <h2>Version comparison</h2>
                  <p>Compare this finalized result with an earlier finalized version.</p>
                </div>
                <select
                  aria-label="Comparison baseline"
                  value={compareId}
                  onChange={(event) => setCompareId(event.target.value)}
                >
                  <option value="">Choose baseline</option>
                  {comparisonOptions.map((item) => (
                    <option key={item.id} value={item.id}>
                      Version {item.version}
                    </option>
                  ))}
                </select>
                <button className="secondary" disabled={!compareId} onClick={compare}>
                  Compare
                </button>
                {comparison ? (
                  <div className="comparison-results">
                    <span>Adjusted score</span>
                    <strong>{comparison.adjusted_score_delta.toFixed(1)}</strong>
                    <span>Confidence</span>
                    <strong>{comparison.confidence_delta.toFixed(2)}</strong>
                    <span>Evidence quality</span>
                    <strong>{comparison.evidence_quality_delta.toFixed(2)}</strong>
                  </div>
                ) : null}
              </section>
            ) : null}
            <WorkflowTimeline status={selected.status} />
          </>
        ) : (
          <section className="empty-workspace">
            <div>
              <h1>No assessments yet</h1>
              <p>Register a system and create an assessment to begin scoring.</p>
              <button className="primary" onClick={() => setShowCreate(true)}>
                Create first assessment
              </button>
            </div>
          </section>
        )}
      </main>
      {showCreate ? (
        <CreateWorkspaceItem
          systems={systems}
          onCreateSystem={createSystem}
          onCreateAssessment={createAssessment}
          onClose={() => setShowCreate(false)}
        />
      ) : null}
    </div>
  )
}

export default App
