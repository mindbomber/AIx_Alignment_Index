from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .orm import Credential, Membership, Organization, User
from .security import hash_token


ROLE_PERMISSIONS = {
    "viewer": {"read"},
    "assessor": {"read", "system:write", "assessment:write", "evidence:write"},
    "reviewer": {"read", "assessment:review"},
    "approver": {"read", "assessment:review", "assessment:approve", "assessment:finalize"},
    "admin": {
        "read",
        "system:write",
        "assessment:write",
        "assessment:review",
        "assessment:approve",
        "assessment:finalize",
        "evidence:write",
        "rubric:write",
        "policy:write",
        "credential:write",
        "privacy:write",
        "webhook:write",
        "audit:read",
    },
    "owner": {"*"},
}

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    organization: Organization
    user: User
    role: str
    credential: Credential

    def permits(self, permission: str) -> bool:
        permissions = ROLE_PERMISSIONS.get(self.role, set())
        return "*" in permissions or permission in permissions


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def current_principal(
    authorization: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if authorization is None or authorization.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer credential required")
    token_hash = hash_token(authorization.credentials, settings.token_pepper)
    credential = db.scalar(
        select(Credential).where(Credential.token_hash == token_hash)
    )
    now = datetime.now(timezone.utc)
    if (
        credential is None
        or credential.revoked_at is not None
        or _aware(credential.expires_at) <= now
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired credential")
    if (
        credential.kind == "session"
        and credential.last_used_at is not None
        and _aware(credential.last_used_at)
        + timedelta(minutes=settings.session_idle_minutes)
        <= now
    ):
        credential.revoked_at = now
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired due to inactivity")
    user = db.get(User, credential.user_id)
    organization = db.get(Organization, credential.organization_id)
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == credential.organization_id,
            Membership.user_id == credential.user_id,
        )
    )
    if (
        not user
        or not user.active
        or not organization
        or not membership
        or not membership.active
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credential principal is inactive")
    if (
        credential.last_used_at is None
        or _aware(credential.last_used_at)
        + timedelta(seconds=settings.session_touch_interval_seconds)
        <= now
    ):
        credential.last_used_at = now
        db.commit()
    return Principal(organization, user, membership.role, credential)


def require(permission: str):
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.permits(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role permission")
        return principal

    return dependency
