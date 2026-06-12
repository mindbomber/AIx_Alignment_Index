from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BootstrapRequest(ApiModel):
    organization_name: str = Field(min_length=2, max_length=200)
    organization_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(ApiModel):
    organization_slug: str
    email: str
    password: str
    mfa_code: str | None = Field(default=None, min_length=6, max_length=32)


class TokenResponse(ApiModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    organization_id: str
    user_id: str
    role: str


class SessionResponse(ApiModel):
    id: str
    name: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    current: bool = False


class ApiKeyRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class OrganizationResponse(ApiModel):
    id: str
    slug: str
    name: str
    require_mfa: bool = False


class PrincipalResponse(ApiModel):
    organization: OrganizationResponse
    user_id: str
    email: str
    display_name: str
    role: str


class MemberCreate(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    role: Literal["owner", "admin", "assessor", "reviewer", "approver", "viewer"]
    password: str | None = Field(default=None, min_length=12, max_length=256)


class MemberResponse(ApiModel):
    user_id: str
    email: str
    display_name: str
    role: str
    active: bool
    mfa_enabled: bool = False
    scim_external_id: str | None = None


class MemberUpdate(ApiModel):
    role: Literal["owner", "admin", "assessor", "reviewer", "approver", "viewer"] | None = None
    active: bool | None = None


class InvitationCreate(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["owner", "admin", "assessor", "reviewer", "approver", "viewer"]
    expires_in_days: int = Field(default=7, ge=1, le=30)


class InvitationResponse(ApiModel):
    id: str
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InvitationCreatedResponse(InvitationResponse):
    invitation_token: str


class InvitationAccept(ApiModel):
    token: str = Field(min_length=20)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=256)


class MfaSetupResponse(ApiModel):
    secret: str
    otpauth_uri: str


class MfaCodeRequest(ApiModel):
    code: str = Field(min_length=6, max_length=32)


class MfaEnableResponse(ApiModel):
    recovery_codes: list[str]


class OrganizationSecurityUpdate(ApiModel):
    require_mfa: bool


class ScimTokenRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    expires_in_days: int = Field(default=365, ge=1, le=3650)


class ScimUserCreate(ApiModel):
    schemas: list[str] = Field(default_factory=list)
    userName: str = Field(min_length=3, max_length=320)
    externalId: str | None = Field(default=None, max_length=255)
    active: bool = True
    displayName: str | None = Field(default=None, max_length=200)
    roles: list[dict[str, Any]] = Field(default_factory=list)


class ScimPatchOperation(ApiModel):
    op: Literal["add", "replace", "remove"]
    path: str | None = None
    value: Any = None


class ScimPatchRequest(ApiModel):
    schemas: list[str] = Field(default_factory=list)
    Operations: list[ScimPatchOperation] = Field(min_length=1)


class SystemCreate(ApiModel):
    name: str = Field(min_length=1, max_length=240)
    kind: str = Field(min_length=1, max_length=80)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemResponse(ApiModel):
    id: str
    organization_id: str
    name: str
    kind: str
    description: str
    metadata_json: dict[str, Any]
    created_by: str
    created_at: datetime
    updated_at: datetime


class AssessmentCreate(ApiModel):
    system_id: str
    rubric_version_id: str | None = None
    previous_version_id: str | None = None
    assessment: dict[str, Any]


class AssessmentUpdate(ApiModel):
    assessment: dict[str, Any]


class AssessmentResponse(ApiModel):
    id: str
    organization_id: str
    system_id: str
    rubric_version_id: str | None
    previous_version_id: str | None
    version: int
    status: str
    input_json: dict[str, Any]
    input_sha256: str | None
    result_json: dict[str, Any] | None
    result_sha256: str | None
    created_by: str
    finalized_by: str | None
    finalized_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AssessmentComparisonResponse(ApiModel):
    baseline_id: str
    candidate_id: str
    baseline_version: int
    candidate_version: int
    adjusted_score_delta: float
    confidence_delta: float
    evidence_quality_delta: float
    constraint_skew_delta: float
    domain_score_deltas: dict[str, float]


class EvidenceCreate(ApiModel):
    indicator_code: str = Field(pattern=r"^(P[1-6]|B[1-6]|C[1-6]|H[1-5]|F[1-6])$")
    source_type: str = Field(min_length=1, max_length=40)
    uri: str = Field(min_length=1)
    object_key: str | None = None
    content_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    trust_score: float = Field(ge=0, le=1)
    freshness_at: datetime | None = None
    classification: Literal["public", "internal", "confidential", "restricted"] = (
        "internal"
    )
    retention_until: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceResponse(ApiModel):
    id: str
    assessment_id: str
    indicator_code: str
    source_type: str
    uri: str
    object_key: str | None
    content_sha256: str
    trust_score: float
    freshness_at: datetime | None
    classification: str
    retention_until: datetime | None
    metadata_json: dict[str, Any]
    scan_status: str
    scanned_at: datetime | None
    created_at: datetime


class LegalHoldCreate(ApiModel):
    evidence_id: str | None = None
    reason: str = Field(min_length=3, max_length=2000)


class LegalHoldResponse(ApiModel):
    id: str
    organization_id: str
    evidence_id: str | None
    reason: str
    created_by: str
    released_by: str | None
    created_at: datetime
    released_at: datetime | None


class PolicyCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    rules: dict[str, Any]
    active: bool = True


class PolicyResponse(ApiModel):
    id: str
    name: str
    rules_json: dict[str, Any]
    active: bool
    created_at: datetime


class RubricCreate(ApiModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,98}[a-z0-9]$")
    version: str = Field(min_length=1, max_length=40)
    content: dict[str, Any]


class RubricResponse(ApiModel):
    id: str
    slug: str
    version: str
    status: str
    content_json: dict[str, Any]
    content_sha256: str
    published_at: datetime | None
    created_at: datetime


class AuditResponse(ApiModel):
    id: str
    actor_user_id: str | None
    action: str
    entity_type: str
    entity_id: str
    payload_json: dict[str, Any]
    previous_hash: str
    event_hash: str
    created_at: datetime


class JobCreate(ApiModel):
    kind: Literal["assessment_report"]
    idempotency_key: str = Field(min_length=8, max_length=120)
    payload: dict[str, Any]
    max_attempts: int = Field(default=3, ge=1, le=10)


class JobResponse(ApiModel):
    id: str
    kind: str
    status: str
    idempotency_key: str
    payload_json: dict[str, Any]
    result_json: dict[str, Any] | None
    error: str | None
    attempts: int
    max_attempts: int
    created_at: datetime
    updated_at: datetime


class WebhookCreate(ApiModel):
    url: str = Field(min_length=8, max_length=2048)
    events: list[str] = Field(min_length=1)


class WebhookResponse(ApiModel):
    id: str
    url: str
    events_json: list[str]
    active: bool
    created_at: datetime
    updated_at: datetime


class WebhookCreatedResponse(WebhookResponse):
    signing_secret: str


class WebhookDeliveryResponse(ApiModel):
    id: str
    endpoint_id: str
    event_id: str
    event_type: str
    status: str
    attempts: int
    max_attempts: int
    response_code: int | None
    error: str | None
    next_attempt_at: datetime
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PrivacyDeleteRequest(ApiModel):
    confirmation: str = Field(min_length=1, max_length=240)


class PrivacyRequestResponse(ApiModel):
    id: str
    organization_id: str
    requested_by: str
    kind: str
    status: str
    scheduled_for: datetime
    result_json: dict[str, Any] | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class ErrorDetail(ApiModel):
    code: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ApiModel):
    error: ErrorDetail
