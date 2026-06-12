import type {
  AssessmentDocument,
  AssessmentComparison,
  AssessmentRecord,
  EvidenceRecord,
  JobRecord,
  InvitationRecord,
  MemberRecord,
  AuditRecord,
  PolicyRecord,
  Principal,
  RubricRecord,
  SystemRecord,
} from './types'

const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type ApiError = { error?: { message?: string; context?: { errors?: unknown[] } } }

export class ApiClient {
  private token: string

  constructor(token: string) {
    this.token = token
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const isForm = init?.body instanceof FormData
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        ...(isForm ? {} : { 'Content-Type': 'application/json' }),
        Authorization: `Bearer ${this.token}`,
        ...init?.headers,
      },
    })
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as ApiError
      throw new Error(body.error?.message ?? `Request failed (${response.status})`)
    }
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  me = () => this.request<Principal>('/v1/me')
  members = () => this.request<MemberRecord[]>('/v1/members')
  invitations = () => this.request<InvitationRecord[]>('/v1/invitations')
  updateMember = (
    userId: string,
    payload: { role?: string; active?: boolean },
  ) =>
    this.request<MemberRecord>(`/v1/members/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
  inviteMember = (payload: { email: string; role: string }) =>
    this.request<InvitationRecord>('/v1/invitations', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  revokeInvitation = (invitationId: string) =>
    this.request<void>(`/v1/invitations/${invitationId}`, { method: 'DELETE' })
  setupMfa = () =>
    this.request<{ secret: string; otpauth_uri: string }>('/v1/auth/mfa/setup', {
      method: 'POST',
    })
  enableMfa = (code: string) =>
    this.request<{ recovery_codes: string[] }>('/v1/auth/mfa/enable', {
      method: 'POST',
      body: JSON.stringify({ code }),
    })
  enforceMfa = (requireMfa: boolean) =>
    this.request<Principal['organization']>('/v1/organization/security', {
      method: 'PATCH',
      body: JSON.stringify({ require_mfa: requireMfa }),
    })
  systems = () => this.request<SystemRecord[]>('/v1/systems')
  rubrics = () => this.request<RubricRecord[]>('/v1/rubrics')
  policies = () => this.request<PolicyRecord[]>('/v1/policies')
  auditEvents = () => this.request<AuditRecord[]>('/v1/audit-events')
  jobs = () => this.request<JobRecord[]>('/v1/jobs')
  assessments = () => this.request<AssessmentRecord[]>('/v1/assessments')
  createSystem = (payload: { name: string; kind: string; description: string }) =>
    this.request<SystemRecord>('/v1/systems', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  createRubric = (payload: {
    slug: string
    version: string
    content: Record<string, unknown>
  }) =>
    this.request<RubricRecord>('/v1/rubrics', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  publishRubric = (rubricId: string) =>
    this.request<RubricRecord>(`/v1/rubrics/${rubricId}/publish`, {
      method: 'POST',
    })
  createPolicy = (payload: {
    name: string
    rules: Record<string, unknown>
    active: boolean
  }) =>
    this.request<PolicyRecord>('/v1/policies', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  createAssessment = (systemId: string, assessment: AssessmentDocument) =>
    this.request<AssessmentRecord>('/v1/assessments', {
      method: 'POST',
      body: JSON.stringify({ system_id: systemId, assessment }),
    })
  evidence = (assessmentId: string) =>
    this.request<EvidenceRecord[]>(`/v1/assessments/${assessmentId}/evidence`)

  saveAssessment = (assessmentId: string, assessment: AssessmentDocument) =>
    this.request<AssessmentRecord>(`/v1/assessments/${assessmentId}`, {
      method: 'PUT',
      body: JSON.stringify({ assessment }),
    })

  transition = (
    assessmentId: string,
    action: 'submit' | 'approve' | 'reject' | 'finalize',
  ) =>
    this.request<AssessmentRecord>(
      `/v1/assessments/${assessmentId}/${action}`,
      { method: 'POST' },
    )

  addEvidence = (
    assessmentId: string,
    payload: Omit<EvidenceRecord, 'id' | 'freshness_at' | 'metadata_json'>,
  ) =>
    this.request<EvidenceRecord>(`/v1/assessments/${assessmentId}/evidence`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })

  uploadEvidence = (
    assessmentId: string,
    payload: {
      indicator_code: string
      source_type: string
      trust_score: number
      classification: string
      file: File
    },
  ) => {
    const body = new FormData()
    body.set('indicator_code', payload.indicator_code)
    body.set('source_type', payload.source_type)
    body.set('trust_score', String(payload.trust_score))
    body.set('classification', payload.classification)
    body.set('file', payload.file)
    return this.request<EvidenceRecord>(
      `/v1/assessments/${assessmentId}/evidence/upload`,
      { method: 'POST', body },
    )
  }

  compare = (baselineId: string, candidateId: string) =>
    this.request<AssessmentComparison>(
      `/v1/assessment-comparisons?baseline_id=${encodeURIComponent(baselineId)}&candidate_id=${encodeURIComponent(candidateId)}`,
    )

  createReport = (assessmentId: string, format = 'markdown') =>
    this.request<JobRecord>('/v1/jobs', {
      method: 'POST',
      body: JSON.stringify({
        kind: 'assessment_report',
        idempotency_key: `web-${assessmentId}-${format}-${crypto.randomUUID()}`,
        payload: { assessment_id: assessmentId, format },
      }),
    })

  job = (jobId: string) => this.request<JobRecord>(`/v1/jobs/${jobId}`)
}

export async function login(
  organization_slug: string,
  email: string,
  password: string,
  mfa_code?: string,
) {
  const response = await fetch(`${baseUrl}/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ organization_slug, email, password, mfa_code }),
  })
  const body = await response.json()
  if (!response.ok) throw new Error(body.error?.message ?? 'Login failed')
  return body.access_token as string
}

export function oidcLoginUrl(organizationSlug: string) {
  return `${baseUrl}/v1/auth/oidc/login?organization_slug=${encodeURIComponent(organizationSlug)}`
}
