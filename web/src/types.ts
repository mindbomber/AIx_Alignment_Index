export type DomainCode = 'P' | 'B' | 'CT' | 'H' | 'F'

export type ScoreEntry = {
  score: number
  evidence_quality: number
  evidence?: string | string[]
  notes?: string
}

export type AssessmentDocument = {
  system: {
    name: string
    type?: string
    unit_of_analysis: string
    reference_population: string
    time_horizon: string
    aggregation_rule: string
    intended_use?: string
  }
  scores: Record<string, ScoreEntry>
  weights?: Record<DomainCode, number>
  optimization_pressure?: number
}

export type AssessmentRecord = {
  id: string
  system_id: string
  version: number
  status: 'draft' | 'in_review' | 'approved' | 'finalized' | 'rejected'
  input_json: AssessmentDocument
  result_json: {
    domain_scores: Record<DomainCode, number>
    adjusted_score: number
    confidence: number
    evidence_quality: number
    constraint_skew: number
  } | null
  input_sha256: string | null
  result_sha256: string | null
}

export type SystemRecord = {
  id: string
  name: string
  kind: string
  description: string
}

export type RubricRecord = {
  id: string
  slug: string
  version: string
  status: string
  content_json: Record<string, unknown>
  content_sha256: string
  published_at: string | null
  created_at: string
}

export type PolicyRecord = {
  id: string
  name: string
  rules_json: Record<string, unknown>
  active: boolean
  created_at: string
}

export type AuditRecord = {
  id: string
  actor_user_id: string | null
  action: string
  entity_type: string
  entity_id: string
  payload_json: Record<string, unknown>
  event_hash: string
  created_at: string
}

export type Principal = {
  organization: { id: string; name: string; slug: string; require_mfa: boolean }
  user_id: string
  email: string
  display_name: string
  role: string
}

export type MemberRecord = {
  user_id: string
  email: string
  display_name: string
  role: string
  active: boolean
  mfa_enabled: boolean
  scim_external_id: string | null
}

export type InvitationRecord = {
  id: string
  email: string
  role: string
  expires_at: string
  accepted_at: string | null
  revoked_at: string | null
  created_at: string
  invitation_token?: string
}

export type EvidenceRecord = {
  id: string
  indicator_code: string
  source_type: string
  uri: string
  content_sha256: string
  trust_score: number
  classification: string
  freshness_at: string | null
  metadata_json: Record<string, unknown>
}

export type JobRecord = {
  id: string
  kind: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  payload_json: Record<string, unknown>
  result_json: { content?: string; format?: string } | null
  error: string | null
  attempts: number
  created_at: string
}

export type AssessmentComparison = {
  baseline_id: string
  candidate_id: string
  baseline_version: number
  candidate_version: number
  adjusted_score_delta: number
  confidence_delta: number
  evidence_quality_delta: number
  constraint_skew_delta: number
  domain_score_deltas: Record<DomainCode, number>
}
