import { useState } from 'react'
import { login, oidcLoginUrl } from '../api'

type Props = { onAuthenticated: (token: string) => void }

export function LoginScreen({ onAuthenticated }: Props) {
  const [organization, setOrganization] = useState('aix-research')
  const [email, setEmail] = useState('owner@example.com')
  const [password, setPassword] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const [mfaRequired, setMfaRequired] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      onAuthenticated(await login(organization, email, password, mfaCode || undefined))
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Login failed'
      if (message === 'MFA code required') setMfaRequired(true)
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-brand">AIx</div>
        <h1 id="login-title">Alignment measurement workspace</h1>
        <p>Sign in to score, review, and publish evidence-backed assessments.</p>
        <form onSubmit={submit}>
          <label>
            Organization
            <input
              value={organization}
              onChange={(event) => setOrganization(event.target.value)}
              autoComplete="organization"
            />
          </label>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </label>
          {mfaRequired ? (
            <label>
              Authenticator or recovery code
              <input
                value={mfaCode}
                onChange={(event) => setMfaCode(event.target.value)}
                autoComplete="one-time-code"
                inputMode="numeric"
              />
            </label>
          ) : null}
          {error ? <div className="form-error">{error}</div> : null}
          <button className="primary wide" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <a className="secondary sso-link" href={oidcLoginUrl(organization)}>
            Continue with organization SSO
          </a>
        </form>
      </section>
      <aside className="login-context">
        <blockquote>
          Interpret the domain vector before the scalar. Evidence, disagreement,
          and lower-layer constraints take priority over the composite.
        </blockquote>
        <span>AIx Expanded Edition</span>
      </aside>
    </main>
  )
}
