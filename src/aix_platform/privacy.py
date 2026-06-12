from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .audit import append_audit_event
from .config import Settings
from .orm import (
    Assessment,
    AuditEvent,
    Credential,
    Evidence,
    Job,
    Invitation,
    LegalHold,
    Membership,
    Organization,
    Policy,
    PolicyDecision,
    PrivacyRequest,
    RubricVersion,
    SystemRecord,
    User,
    UserMfa,
    WebhookDelivery,
    WebhookEndpoint,
)
from .storage import object_store


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row(record, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: _json_value(getattr(record, field)) for field in fields}


def organization_export(db: Session, organization_id: str) -> dict[str, Any]:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise ValueError("Organization not found")
    memberships = list(
        db.scalars(
            select(Membership).where(Membership.organization_id == organization_id)
        )
    )
    users = [db.get(User, membership.user_id) for membership in memberships]

    def records(model):
        return list(
            db.scalars(
                select(model).where(model.organization_id == organization_id)
            )
        )

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "organization": _row(organization, ("id", "slug", "name", "created_at")),
        "members": [
            {
                **_row(membership, ("id", "user_id", "role", "created_at")),
                "email": user.email if user else None,
                "display_name": user.display_name if user else None,
                "active": user.active if user else None,
            }
            for membership, user in zip(memberships, users)
        ],
        "systems": [
            _row(
                record,
                (
                    "id",
                    "name",
                    "kind",
                    "description",
                    "metadata_json",
                    "created_by",
                    "created_at",
                    "updated_at",
                ),
            )
            for record in records(SystemRecord)
        ],
        "rubrics": [
            _row(
                record,
                (
                    "id",
                    "slug",
                    "version",
                    "status",
                    "content_json",
                    "content_sha256",
                    "created_by",
                    "published_at",
                    "created_at",
                ),
            )
            for record in records(RubricVersion)
        ],
        "assessments": [
            _row(
                record,
                (
                    "id",
                    "system_id",
                    "rubric_version_id",
                    "previous_version_id",
                    "version",
                    "status",
                    "input_json",
                    "input_sha256",
                    "result_json",
                    "result_sha256",
                    "created_by",
                    "finalized_by",
                    "finalized_at",
                    "created_at",
                    "updated_at",
                ),
            )
            for record in records(Assessment)
        ],
        "evidence": [
            _row(
                record,
                (
                    "id",
                    "assessment_id",
                    "indicator_code",
                    "source_type",
                    "uri",
                    "object_key",
                    "content_sha256",
                    "trust_score",
                    "freshness_at",
                    "classification",
                    "retention_until",
                    "metadata_json",
                    "created_by",
                    "created_at",
                ),
            )
            for record in records(Evidence)
        ],
        "legal_holds": [
            _row(
                record,
                (
                    "id",
                    "evidence_id",
                    "reason",
                    "created_by",
                    "released_by",
                    "created_at",
                    "released_at",
                ),
            )
            for record in records(LegalHold)
        ],
        "policies": [
            _row(
                record,
                ("id", "name", "rules_json", "active", "created_by", "created_at"),
            )
            for record in records(Policy)
        ],
        "audit_events": [
            _row(
                record,
                (
                    "id",
                    "actor_user_id",
                    "action",
                    "entity_type",
                    "entity_id",
                    "payload_json",
                    "previous_hash",
                    "event_hash",
                    "created_at",
                ),
            )
            for record in records(AuditEvent)
        ],
        "webhooks": [
            _row(record, ("id", "url", "events_json", "active", "created_at"))
            for record in records(WebhookEndpoint)
        ],
    }


def purge_expired_evidence(db: Session, settings: Settings) -> int:
    now = datetime.now(timezone.utc)
    expired = list(
        db.scalars(
            select(Evidence).where(
                Evidence.retention_until.is_not(None),
                Evidence.retention_until <= now,
                ~select(LegalHold.id)
                .where(
                    LegalHold.organization_id == Evidence.organization_id,
                    LegalHold.released_at.is_(None),
                    (LegalHold.evidence_id.is_(None))
                    | (LegalHold.evidence_id == Evidence.id),
                )
                .exists(),
            )
        )
    )
    store = object_store(settings)
    for evidence in expired:
        if evidence.object_key:
            store.delete(evidence.object_key)
        append_audit_event(
            db,
            organization_id=evidence.organization_id,
            actor_user_id=None,
            action="evidence.retention_purge",
            entity_type="evidence",
            entity_id=evidence.id,
            payload={"content_sha256": evidence.content_sha256},
        )
        db.delete(evidence)
    db.commit()
    return len(expired)


def process_next_privacy_request(
    db: Session,
    settings: Settings,
) -> PrivacyRequest | None:
    now = datetime.now(timezone.utc)
    request = db.scalar(
        select(PrivacyRequest)
        .where(
            PrivacyRequest.status == "pending",
            PrivacyRequest.scheduled_for <= now,
        )
        .order_by(PrivacyRequest.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if request is None:
        return None
    request.status = "running"
    db.commit()
    try:
        if request.kind == "export":
            request.result_json = organization_export(db, request.organization_id)
            request.status = "completed"
        elif request.kind == "delete":
            _delete_organization(db, request.organization_id, settings)
            request.status = "completed"
            request.result_json = {"deleted": True}
        else:
            raise ValueError(f"Unsupported privacy request kind: {request.kind}")
        request.completed_at = datetime.now(timezone.utc)
        request.error = None
    except Exception as exc:
        request.status = "failed"
        request.error = str(exc)[:2000]
    db.commit()
    return request


def _delete_organization(
    db: Session,
    organization_id: str,
    settings: Settings,
) -> None:
    active_hold = db.scalar(
        select(LegalHold.id).where(
            LegalHold.organization_id == organization_id,
            LegalHold.released_at.is_(None),
        )
    )
    if active_hold:
        raise ValueError("Organization deletion is blocked by an active legal hold")
    evidence = list(
        db.scalars(
            select(Evidence).where(Evidence.organization_id == organization_id)
        )
    )
    store = object_store(settings)
    for record in evidence:
        if record.object_key:
            store.delete(record.object_key)
    member_user_ids = list(
        db.scalars(
            select(Membership.user_id).where(
                Membership.organization_id == organization_id
            )
        )
    )
    for model in (
        WebhookDelivery,
        PolicyDecision,
        LegalHold,
        Evidence,
        Job,
        Assessment,
        RubricVersion,
        Policy,
        SystemRecord,
        AuditEvent,
        Credential,
        WebhookEndpoint,
        Invitation,
        Membership,
    ):
        db.execute(
            delete(model).where(model.organization_id == organization_id),
            execution_options={"synchronize_session": False},
        )
    db.execute(delete(Organization).where(Organization.id == organization_id))
    db.flush()
    for user_id in member_user_ids:
        remaining = db.scalar(
            select(Membership.id).where(Membership.user_id == user_id).limit(1)
        )
        if remaining is None:
            db.execute(delete(UserMfa).where(UserMfa.user_id == user_id))
            db.execute(delete(User).where(User.id == user_id))
