from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .canonical import content_hash
from .orm import AuditEvent, Organization


GENESIS_HASH = "0" * 64


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def append_audit_event(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict | None = None,
) -> AuditEvent:
    # Lock the tenant row so concurrent writers cannot create two events with
    # the same predecessor. SQLite ignores this lock; deployed PostgreSQL does not.
    db.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update()
    )
    previous = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.organization_id == organization_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    created_at = datetime.now(timezone.utc)
    previous_hash = previous.event_hash if previous else GENESIS_HASH
    event_payload = {
        "organization_id": organization_id,
        "actor_user_id": actor_user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload": payload or {},
        "previous_hash": previous_hash,
        "created_at": _timestamp(created_at),
    }
    event = AuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=payload or {},
        previous_hash=previous_hash,
        event_hash=content_hash(event_payload),
        created_at=created_at,
    )
    db.add(event)
    return event


def verify_audit_chain(events: list[AuditEvent]) -> bool:
    previous_hash = GENESIS_HASH
    for event in events:
        payload = {
            "organization_id": event.organization_id,
            "actor_user_id": event.actor_user_id,
            "action": event.action,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "payload": event.payload_json,
            "previous_hash": previous_hash,
            "created_at": _timestamp(event.created_at),
        }
        if event.previous_hash != previous_hash or event.event_hash != content_hash(payload):
            return False
        previous_hash = event.event_hash
    return True
