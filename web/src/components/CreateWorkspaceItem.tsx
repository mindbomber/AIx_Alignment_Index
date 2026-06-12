import { useState } from 'react'
import type { SystemRecord } from '../types'

type Props = {
  systems: SystemRecord[]
  onCreateSystem: (payload: {
    name: string
    kind: string
    description: string
  }) => Promise<SystemRecord>
  onCreateAssessment: (system: SystemRecord) => Promise<void>
  onClose: () => void
}

export function CreateWorkspaceItem({
  systems,
  onCreateSystem,
  onCreateAssessment,
  onClose,
}: Props) {
  const [mode, setMode] = useState<'assessment' | 'system'>(
    systems.length ? 'assessment' : 'system',
  )
  const [systemId, setSystemId] = useState(systems[0]?.id ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const form = new FormData(event.currentTarget)
    try {
      if (mode === 'system') {
        const system = await onCreateSystem({
          name: String(form.get('name')),
          kind: String(form.get('kind')),
          description: String(form.get('description')),
        })
        if (form.get('create_assessment') === 'yes') {
          await onCreateAssessment(system)
        }
      } else {
        const system = systems.find((item) => item.id === systemId)
        if (!system) throw new Error('Choose a registered system')
        await onCreateAssessment(system)
      }
      onClose()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create item')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="create-title">
        <header>
          <div>
            <span>Workspace setup</span>
            <h2 id="create-title">Create {mode}</h2>
          </div>
          <button type="button" className="text-button" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="dialog-tabs">
          <button
            type="button"
            className={mode === 'assessment' ? 'active' : ''}
            disabled={!systems.length}
            onClick={() => setMode('assessment')}
          >
            Assessment
          </button>
          <button
            type="button"
            className={mode === 'system' ? 'active' : ''}
            onClick={() => setMode('system')}
          >
            System
          </button>
        </div>
        <form onSubmit={submit}>
          {mode === 'assessment' ? (
            <label>
              Registered system
              <select
                value={systemId}
                onChange={(event) => setSystemId(event.target.value)}
                required
              >
                {systems.map((system) => (
                  <option key={system.id} value={system.id}>
                    {system.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <>
              <label>
                System name
                <input name="name" required maxLength={240} autoFocus />
              </label>
              <label>
                System type
                <select name="kind" defaultValue="ai_system">
                  <option value="ai_system">AI system</option>
                  <option value="platform">Platform</option>
                  <option value="institution">Institution</option>
                  <option value="process">Process</option>
                </select>
              </label>
              <label>
                Description
                <textarea name="description" rows={4} />
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  name="create_assessment"
                  value="yes"
                  defaultChecked
                />
                Create an initial assessment
              </label>
            </>
          )}
          {error ? <div className="form-error">{error}</div> : null}
          <button className="primary" disabled={busy}>
            {busy ? 'Creating…' : `Create ${mode}`}
          </button>
        </form>
      </section>
    </div>
  )
}
