import { useEffect, useState } from 'react'
import { ApiClient } from '../api'
import type { InvitationRecord, MemberRecord, Principal } from '../types'

const roles = ['owner', 'admin', 'assessor', 'reviewer', 'approver', 'viewer']

type Props = {
  client: ApiClient
  principal: Principal
  onOrganizationChange: (organization: Principal['organization']) => void
}

export function AdminIdentity({
  client,
  principal,
  onOrganizationChange,
}: Props) {
  const [members, setMembers] = useState<MemberRecord[]>([])
  const [invitations, setInvitations] = useState<InvitationRecord[]>([])
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('viewer')
  const [setupSecret, setSetupSecret] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  async function reload() {
    const [loadedMembers, loadedInvitations] = await Promise.all([
      client.members(),
      client.invitations(),
    ])
    setMembers(loadedMembers)
    setInvitations(loadedInvitations)
  }

  useEffect(() => {
    let cancelled = false
    Promise.all([client.members(), client.invitations()])
      .then(([loadedMembers, loadedInvitations]) => {
        if (cancelled) return
        setMembers(loadedMembers)
        setInvitations(loadedInvitations)
      })
      .catch((reason) => {
        if (cancelled) return
        setError(
          reason instanceof Error ? reason.message : 'Could not load identity settings',
        )
      })
    return () => {
      cancelled = true
    }
  }, [client])

  async function updateMember(
    member: MemberRecord,
    payload: { role?: string; active?: boolean },
  ) {
    setError('')
    try {
      const updated = await client.updateMember(member.user_id, payload)
      setMembers((current) =>
        current.map((item) => (item.user_id === updated.user_id ? updated : item)),
      )
      setNotice('Member access updated')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update member')
    }
  }

  async function invite() {
    setError('')
    try {
      const invitation = await client.inviteMember({ email, role })
      setInvitations((current) => [invitation, ...current])
      setNotice(`Invitation token: ${invitation.invitation_token}`)
      setEmail('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create invitation')
    }
  }

  async function beginMfa() {
    setError('')
    try {
      const setup = await client.setupMfa()
      setSetupSecret(setup.secret)
      setNotice('Add the secret to your authenticator, then verify a code.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not start MFA setup')
    }
  }

  async function enableMfa() {
    setError('')
    try {
      const enabled = await client.enableMfa(mfaCode)
      setRecoveryCodes(enabled.recovery_codes)
      setSetupSecret('')
      setMfaCode('')
      await reload()
      setNotice('MFA enabled. Store the recovery codes securely.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not enable MFA')
    }
  }

  return (
    <section className="admin-page">
      <header>
        <div>
          <h1>Identity and access</h1>
          <p>Manage organization membership, provisioning, and sign-in assurance.</p>
        </div>
        <label className="mfa-policy">
          <input
            type="checkbox"
            checked={principal.organization.require_mfa}
            onChange={async (event) => {
              try {
                const organization = await client.enforceMfa(event.target.checked)
                onOrganizationChange(organization)
                setNotice(
                  organization.require_mfa
                    ? 'Organization MFA enforcement enabled'
                    : 'Organization MFA enforcement disabled',
                )
              } catch (reason) {
                setError(
                  reason instanceof Error ? reason.message : 'Could not update MFA policy',
                )
              }
            }}
          />
          Require MFA for active members
        </label>
      </header>
      {(notice || error) && (
        <div className={error ? 'notice error' : 'notice'} role="status">
          {error || notice}
        </div>
      )}
      <div className="admin-grid">
        <article className="admin-card members-card">
          <div className="card-heading">
            <div>
              <h2>Members</h2>
              <p>Role changes revoke active credentials.</p>
            </div>
            <span>{members.length}</span>
          </div>
          <div className="member-table">
            {members.map((member) => (
              <div className="member-row" key={member.user_id}>
                <div>
                  <strong>{member.display_name}</strong>
                  <small>{member.email}</small>
                </div>
                <span className={member.mfa_enabled ? 'assurance on' : 'assurance'}>
                  {member.mfa_enabled ? 'MFA' : 'No MFA'}
                </span>
                <select
                  aria-label={`Role for ${member.email}`}
                  value={member.role}
                  onChange={(event) => updateMember(member, { role: event.target.value })}
                >
                  {roles.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <button
                  className="secondary"
                  type="button"
                  onClick={() => updateMember(member, { active: !member.active })}
                >
                  {member.active ? 'Deactivate' : 'Activate'}
                </button>
              </div>
            ))}
          </div>
        </article>
        <article className="admin-card">
          <h2>Invite member</h2>
          <label>
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label>
            Initial role
            <select value={role} onChange={(event) => setRole(event.target.value)}>
              {roles.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <button className="primary" disabled={!email} onClick={invite}>
            Create invitation
          </button>
          <div className="pending-invitations">
            {invitations
              .filter((item) => !item.accepted_at && !item.revoked_at)
              .map((invitation) => (
                <div key={invitation.id}>
                  <span>
                    <strong>{invitation.email}</strong>
                    <small>{invitation.role}</small>
                  </span>
                  <button
                    type="button"
                    onClick={async () => {
                      await client.revokeInvitation(invitation.id)
                      await reload()
                    }}
                  >
                    Revoke
                  </button>
                </div>
              ))}
          </div>
        </article>
        <article className="admin-card">
          <h2>Your multi-factor authentication</h2>
          {!setupSecret ? (
            <button className="secondary" onClick={beginMfa}>
              Set up authenticator
            </button>
          ) : (
            <>
              <p className="secret-value">{setupSecret}</p>
              <label>
                Verification code
                <input
                  inputMode="numeric"
                  value={mfaCode}
                  onChange={(event) => setMfaCode(event.target.value)}
                />
              </label>
              <button className="primary" disabled={!mfaCode} onClick={enableMfa}>
                Enable MFA
              </button>
            </>
          )}
          {recoveryCodes.length ? (
            <pre className="recovery-codes">{recoveryCodes.join('\n')}</pre>
          ) : null}
        </article>
      </div>
    </section>
  )
}
