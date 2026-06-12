from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from aix.models import AssessmentValidationError, validate_assessment
from aix.scoring import score_assessment

from .audit import append_audit_event
from .auth import Principal, current_principal, require
from .canonical import content_hash
from .config import Settings, get_settings
from .database import Base, engine, get_db
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
from .policy import evaluate_policy
from .observability import install_observability
from .request_controls import install_request_controls
from .schemas import (
    ApiKeyRequest,
    AssessmentCreate,
    AssessmentComparisonResponse,
    AssessmentResponse,
    AssessmentUpdate,
    AuditResponse,
    BootstrapRequest,
    ErrorResponse,
    EvidenceCreate,
    EvidenceResponse,
    InvitationAccept,
    InvitationCreate,
    InvitationCreatedResponse,
    InvitationResponse,
    LoginRequest,
    JobCreate,
    JobResponse,
    LegalHoldCreate,
    LegalHoldResponse,
    MemberCreate,
    MemberResponse,
    MemberUpdate,
    MfaCodeRequest,
    MfaEnableResponse,
    MfaSetupResponse,
    OrganizationSecurityUpdate,
    OrganizationResponse,
    PolicyCreate,
    PolicyResponse,
    PrivacyDeleteRequest,
    PrivacyRequestResponse,
    PrincipalResponse,
    RubricCreate,
    RubricResponse,
    ScimPatchRequest,
    ScimTokenRequest,
    ScimUserCreate,
    SessionResponse,
    SystemCreate,
    SystemResponse,
    TokenResponse,
    WebhookCreate,
    WebhookCreatedResponse,
    WebhookDeliveryResponse,
    WebhookResponse,
)
from .identity import seal_mfa_secret, unseal_mfa_secret, verify_mfa_code
from .job_queue import enqueue_job
from .security import (
    expires_in,
    hash_password,
    hash_token,
    new_recovery_codes,
    new_token,
    new_totp_secret,
    verify_password,
    verify_totp,
)
from .storage import (
    evidence_object_key,
    iter_file,
    object_store,
    store_upload,
)
from .webhooks import (
    enqueue_webhook_event,
    seal_secret,
    validate_webhook_url,
)


def _error(code: str, message: str, context: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "context": context or {}}}


def _tenant_get(
    db: Session,
    model,
    object_id: str,
    organization_id: str,
):
    record = db.scalar(
        select(model).where(
            model.id == object_id,
            model.organization_id == organization_id,
        )
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    return record


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _issue_credential(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    kind: str,
    name: str,
    expires_at: datetime,
    settings: Settings,
) -> tuple[str, Credential]:
    token = new_token("aixs" if kind == "session" else "aixk")
    credential = Credential(
        organization_id=organization_id,
        user_id=user_id,
        kind=kind,
        name=name,
        token_hash=hash_token(token, settings.token_pepper),
        expires_at=expires_at,
        last_used_at=(
            datetime.now(timezone.utc) if kind == "session" else None
        ),
    )
    db.add(credential)
    db.flush()
    if kind == "session":
        active_sessions = list(
            db.scalars(
                select(Credential)
                .where(
                    Credential.organization_id == organization_id,
                    Credential.user_id == user_id,
                    Credential.kind == "session",
                    Credential.revoked_at.is_(None),
                    Credential.id != credential.id,
                )
                .order_by(Credential.last_used_at, Credential.created_at)
            )
        )
        excess = len(active_sessions) - settings.max_sessions_per_user + 1
        for old_session in active_sessions[: max(0, excess)]:
            old_session.revoked_at = datetime.now(timezone.utc)
    return token, credential


def _member_response(
    db: Session, user: User, membership: Membership
) -> MemberResponse:
    mfa = db.get(UserMfa, user.id)
    return MemberResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
        active=user.active and membership.active,
        mfa_enabled=bool(mfa and mfa.enabled_at),
        scim_external_id=membership.scim_external_id,
    )


def _active_owner_count(db: Session, organization_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Membership)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == organization_id,
                Membership.role == "owner",
                Membership.active.is_(True),
                User.active.is_(True),
            )
        )
        or 0
    )


def _scim_principal(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.credential.kind != "scim":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "A SCIM provisioning token is required"
        )
    return principal


def _scim_role(roles: list[dict[str, Any]]) -> str:
    allowed = {"owner", "admin", "assessor", "reviewer", "approver", "viewer"}
    for role in roles:
        value = role.get("value")
        if value in allowed:
            return str(value)
    return "viewer"


def _scim_user(user: User, membership: Membership) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": user.id,
        "externalId": membership.scim_external_id,
        "userName": user.email,
        "displayName": user.display_name,
        "active": user.active and membership.active,
        "roles": [{"value": membership.role, "primary": True}],
        "meta": {"resourceType": "User", "created": membership.created_at.isoformat()},
    }


def create_app(
    *,
    settings: Settings | None = None,
    create_schema: bool | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(
        title="AIx Platform API",
        version="0.1.0",
        description=(
            "Multi-tenant workflow and evidence API for the AIx measurement framework."
        ),
        responses={
            400: {"model": ErrorResponse},
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=active_settings.token_pepper,
        same_site="lax",
        https_only=active_settings.environment == "production",
        max_age=600,
    )
    install_request_controls(app, active_settings)
    install_observability(app, active_settings)
    oauth = OAuth()
    if active_settings.oidc_issuer:
        oauth.register(
            name="oidc",
            client_id=active_settings.oidc_client_id,
            client_secret=active_settings.oidc_client_secret.get_secret_value()
            if active_settings.oidc_client_secret
            else None,
            server_metadata_url=(
                active_settings.oidc_issuer.rstrip("/")
                + "/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )

    if create_schema if create_schema is not None else active_settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error(f"http_{exc.status_code}", detail),
            headers=exc.headers,
        )

    @app.exception_handler(AssessmentValidationError)
    async def assessment_error(_: Request, exc: AssessmentValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error(
                "invalid_assessment",
                "Assessment validation failed",
                {"errors": exc.errors},
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error(
                "invalid_request",
                "Request validation failed",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, __: IntegrityError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error("conflict", "Resource conflicts with an existing record"),
        )

    @app.get("/health/live", tags=["health"])
    def live() -> dict:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready(db: Session = Depends(get_db)) -> dict:
        db.scalar(select(func.count()).select_from(Organization))
        return {"status": "ready"}

    @app.post("/v1/bootstrap", response_model=TokenResponse, tags=["authentication"])
    def bootstrap(
        payload: BootstrapRequest,
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> TokenResponse | RedirectResponse:
        if db.scalar(select(func.count()).select_from(Organization)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Platform is already bootstrapped")
        organization = Organization(
            name=payload.organization_name,
            slug=payload.organization_slug,
        )
        user = User(
            email=payload.email.lower(),
            display_name=payload.display_name,
            password_hash=hash_password(payload.password),
        )
        db.add_all([organization, user])
        db.flush()
        membership = Membership(
            organization_id=organization.id,
            user_id=user.id,
            role="owner",
        )
        db.add(membership)
        expires_at = expires_in(minutes=settings_value.token_ttl_minutes)
        token, credential = _issue_credential(
            db,
            organization_id=organization.id,
            user_id=user.id,
            kind="session",
            name="bootstrap",
            expires_at=expires_at,
            settings=settings_value,
        )
        append_audit_event(
            db,
            organization_id=organization.id,
            actor_user_id=user.id,
            action="organization.bootstrap",
            entity_type="organization",
            entity_id=organization.id,
        )
        db.commit()
        return TokenResponse(
            access_token=token,
            expires_at=credential.expires_at,
            organization_id=organization.id,
            user_id=user.id,
            role="owner",
        )

    @app.post("/v1/auth/login", response_model=TokenResponse, tags=["authentication"])
    def login(
        payload: LoginRequest,
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> TokenResponse:
        organization = db.scalar(
            select(Organization).where(Organization.slug == payload.organization_slug)
        )
        user = db.scalar(select(User).where(User.email == payload.email.lower()))
        if not organization or not user or not verify_password(
            payload.password, user.password_hash
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        membership = db.scalar(
            select(Membership).where(
                Membership.organization_id == organization.id,
                Membership.user_id == user.id,
            )
        )
        if not membership or not membership.active or not user.active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        mfa = db.get(UserMfa, user.id)
        if mfa and mfa.enabled_at:
            if not payload.mfa_code:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA code required")
            if not verify_mfa_code(
                db,
                user_id=user.id,
                code=payload.mfa_code,
                settings=settings_value,
            ):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid MFA code")
        elif organization.require_mfa:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Organization requires MFA enrollment",
            )
        expires_at = expires_in(minutes=settings_value.token_ttl_minutes)
        token, credential = _issue_credential(
            db,
            organization_id=organization.id,
            user_id=user.id,
            kind="session",
            name="login",
            expires_at=expires_at,
            settings=settings_value,
        )
        append_audit_event(
            db,
            organization_id=organization.id,
            actor_user_id=user.id,
            action="authentication.login",
            entity_type="credential",
            entity_id=credential.id,
        )
        db.commit()
        return TokenResponse(
            access_token=token,
            expires_at=credential.expires_at,
            organization_id=organization.id,
            user_id=user.id,
            role=membership.role,
        )

    @app.get("/v1/auth/oidc/login", tags=["authentication"])
    async def oidc_login(
        request: Request,
        organization_slug: str,
        db: Session = Depends(get_db),
    ):
        oidc_client = getattr(oauth, "oidc", None)
        if not active_settings.oidc_issuer or oidc_client is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "OIDC is not configured",
            )
        organization = db.scalar(
            select(Organization).where(
                Organization.slug == organization_slug
            )
        )
        if organization is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Organization not found"
            )
        request.session["aix_oidc_org"] = organization_slug
        return await oidc_client.authorize_redirect(
            request, active_settings.oidc_redirect_uri
        )

    @app.get(
        "/v1/auth/oidc/callback",
        response_model=TokenResponse,
        tags=["authentication"],
    )
    async def oidc_callback(
        request: Request,
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> TokenResponse:
        oidc_client = getattr(oauth, "oidc", None)
        if not active_settings.oidc_issuer or oidc_client is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "OIDC is not configured",
            )
        organization_slug = request.session.pop("aix_oidc_org", None)
        if not organization_slug:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "OIDC organization state is missing or expired",
            )
        try:
            token = await oidc_client.authorize_access_token(request)
        except OAuthError as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                f"OIDC authentication failed: {exc.error}",
            ) from exc
        userinfo = token.get("userinfo")
        if not userinfo:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "OIDC provider did not return verified user information",
            )
        email = str(userinfo.get("email", "")).lower()
        if not email or userinfo.get("email_verified") is False:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "OIDC account must have a verified email address",
            )
        organization = db.scalar(
            select(Organization).where(
                Organization.slug == organization_slug
            )
        )
        if organization is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Organization not found"
            )
        user = db.scalar(select(User).where(User.email == email))
        membership = None
        if user:
            membership = db.scalar(
                select(Membership).where(
                    Membership.organization_id == organization.id,
                    Membership.user_id == user.id,
                )
            )
        if membership is None:
            if not settings_value.oidc_auto_provision:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "OIDC user is not provisioned for this organization",
                )
            if user is None:
                user = User(
                    email=email,
                    display_name=str(
                        userinfo.get("name")
                        or userinfo.get("preferred_username")
                        or email
                    ),
                    password_hash=hash_password(new_token("oidc")),
                )
                db.add(user)
                db.flush()
            claimed_role = userinfo.get(settings_value.oidc_role_claim)
            allowed_roles = {
                "owner",
                "admin",
                "assessor",
                "reviewer",
                "approver",
                "viewer",
            }
            role = (
                claimed_role
                if isinstance(claimed_role, str)
                and claimed_role in allowed_roles
                else settings_value.oidc_default_role
            )
            membership = Membership(
                organization_id=organization.id,
                user_id=user.id,
                role=role,
            )
            db.add(membership)
            db.flush()
        if not user.active or not membership.active:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "OIDC principal is inactive",
            )
        if organization.require_mfa:
            mfa = db.get(UserMfa, user.id)
            if mfa is None or mfa.enabled_at is None:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "Organization requires MFA enrollment",
                )
        expires_at = expires_in(minutes=settings_value.token_ttl_minutes)
        access_token, credential = _issue_credential(
            db,
            organization_id=organization.id,
            user_id=user.id,
            kind="session",
            name=f"oidc:{userinfo.get('sub', 'unknown')}",
            expires_at=expires_at,
            settings=settings_value,
        )
        append_audit_event(
            db,
            organization_id=organization.id,
            actor_user_id=user.id,
            action="authentication.oidc_login",
            entity_type="credential",
            entity_id=credential.id,
            payload={
                "issuer": settings_value.oidc_issuer,
                "subject": userinfo.get("sub"),
            },
        )
        db.commit()
        response = TokenResponse(
            access_token=access_token,
            expires_at=credential.expires_at,
            organization_id=organization.id,
            user_id=user.id,
            role=membership.role,
        )
        if settings_value.oidc_web_app_url:
            return RedirectResponse(
                f"{settings_value.oidc_web_app_url.rstrip('/')}/"
                f"#access_token={quote(access_token, safe='')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return response

    @app.get("/v1/me", response_model=PrincipalResponse, tags=["authentication"])
    def me(principal: Principal = Depends(current_principal)) -> PrincipalResponse:
        return PrincipalResponse(
            organization=OrganizationResponse.model_validate(principal.organization),
            user_id=principal.user.id,
            email=principal.user.email,
            display_name=principal.user.display_name,
            role=principal.role,
        )

    @app.get(
        "/v1/auth/sessions",
        response_model=list[SessionResponse],
        tags=["authentication"],
    )
    def list_sessions(
        principal: Principal = Depends(current_principal),
        db: Session = Depends(get_db),
    ) -> list[SessionResponse]:
        sessions = list(
            db.scalars(
                select(Credential)
                .where(
                    Credential.organization_id == principal.organization.id,
                    Credential.user_id == principal.user.id,
                    Credential.kind == "session",
                    Credential.revoked_at.is_(None),
                )
                .order_by(Credential.created_at.desc())
            )
        )
        return [
            SessionResponse(
                id=session.id,
                name=session.name,
                created_at=session.created_at,
                last_used_at=session.last_used_at,
                expires_at=session.expires_at,
                current=session.id == principal.credential.id,
            )
            for session in sessions
        ]

    @app.delete(
        "/v1/auth/sessions/{session_id}",
        status_code=204,
        tags=["authentication"],
    )
    def revoke_session(
        session_id: str,
        principal: Principal = Depends(current_principal),
        db: Session = Depends(get_db),
    ) -> None:
        session = db.scalar(
            select(Credential).where(
                Credential.id == session_id,
                Credential.organization_id == principal.organization.id,
                Credential.user_id == principal.user.id,
                Credential.kind == "session",
            )
        )
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
        session.revoked_at = datetime.now(timezone.utc)
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="authentication.session_revoke",
            entity_type="credential",
            entity_id=session.id,
        )
        db.commit()

    @app.post("/v1/auth/logout", status_code=204, tags=["authentication"])
    def logout(
        principal: Principal = Depends(current_principal),
        db: Session = Depends(get_db),
    ) -> None:
        principal.credential.revoked_at = datetime.now(timezone.utc)
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="authentication.logout",
            entity_type="credential",
            entity_id=principal.credential.id,
        )
        db.commit()

    @app.post("/v1/auth/logout-all", status_code=204, tags=["authentication"])
    def logout_all(
        principal: Principal = Depends(current_principal),
        db: Session = Depends(get_db),
    ) -> None:
        now = datetime.now(timezone.utc)
        sessions = list(
            db.scalars(
                select(Credential).where(
                    Credential.organization_id == principal.organization.id,
                    Credential.user_id == principal.user.id,
                    Credential.kind == "session",
                    Credential.revoked_at.is_(None),
                )
            )
        )
        for session in sessions:
            session.revoked_at = now
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="authentication.logout_all",
            entity_type="user",
            entity_id=principal.user.id,
            payload={"revoked_sessions": len(sessions)},
        )
        db.commit()

    @app.post("/v1/members", response_model=MemberResponse, status_code=201)
    def create_member(
        payload: MemberCreate,
        principal: Principal = Depends(require("credential:write")),
        db: Session = Depends(get_db),
    ) -> MemberResponse:
        email = payload.email.lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            if payload.password is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "A password is required for a new local user",
                )
            user = User(
                email=email,
                display_name=payload.display_name,
                password_hash=hash_password(payload.password),
            )
            db.add(user)
            db.flush()
        existing = db.scalar(
            select(Membership).where(
                Membership.organization_id == principal.organization.id,
                Membership.user_id == user.id,
            )
        )
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "User is already a member")
        membership = Membership(
            organization_id=principal.organization.id,
            user_id=user.id,
            role=payload.role,
        )
        db.add(membership)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="membership.create",
            entity_type="membership",
            entity_id=membership.id,
            payload={"user_id": user.id, "role": payload.role},
        )
        db.commit()
        return _member_response(db, user, membership)

    @app.get("/v1/members", response_model=list[MemberResponse])
    def list_members(
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> list[MemberResponse]:
        rows = db.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == principal.organization.id)
            .order_by(User.email)
        )
        return [
            _member_response(db, user, membership)
            for user, membership in rows
        ]

    @app.patch("/v1/members/{user_id}", response_model=MemberResponse)
    def update_member(
        user_id: str,
        payload: MemberUpdate,
        principal: Principal = Depends(require("credential:write")),
        db: Session = Depends(get_db),
    ) -> MemberResponse:
        row = db.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == principal.organization.id,
                Membership.user_id == user_id,
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
        user, membership = row
        removes_owner = membership.role == "owner" and (
            (payload.role is not None and payload.role != "owner")
            or payload.active is False
        )
        if removes_owner and _active_owner_count(db, principal.organization.id) <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Organization must retain at least one active owner",
            )
        old_role = membership.role
        if payload.role is not None:
            membership.role = payload.role
        if payload.active is not None:
            membership.active = payload.active
        if old_role != membership.role or payload.active is False:
            now = datetime.now(timezone.utc)
            for credential in db.scalars(
                select(Credential).where(
                    Credential.organization_id == principal.organization.id,
                    Credential.user_id == user.id,
                    Credential.revoked_at.is_(None),
                )
            ):
                credential.revoked_at = now
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="membership.update",
            entity_type="membership",
            entity_id=membership.id,
            payload={"role": membership.role, "active": membership.active},
        )
        db.commit()
        return _member_response(db, user, membership)

    @app.post(
        "/v1/invitations",
        response_model=InvitationCreatedResponse,
        status_code=201,
    )
    def create_invitation(
        payload: InvitationCreate,
        principal: Principal = Depends(require("credential:write")),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> InvitationCreatedResponse:
        email = payload.email.lower()
        existing_user = db.scalar(select(User).where(User.email == email))
        if existing_user and db.scalar(
            select(Membership).where(
                Membership.organization_id == principal.organization.id,
                Membership.user_id == existing_user.id,
            )
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "User is already a member")
        now = datetime.now(timezone.utc)
        for invitation in db.scalars(
            select(Invitation).where(
                Invitation.organization_id == principal.organization.id,
                Invitation.email == email,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
        ):
            invitation.revoked_at = now
        token = new_token("aixi")
        invitation = Invitation(
            organization_id=principal.organization.id,
            email=email,
            role=payload.role,
            token_hash=hash_token(token, settings_value.token_pepper),
            invited_by=principal.user.id,
            expires_at=expires_in(days=payload.expires_in_days),
        )
        db.add(invitation)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="invitation.create",
            entity_type="invitation",
            entity_id=invitation.id,
            payload={"email": email, "role": payload.role},
        )
        db.commit()
        return InvitationCreatedResponse(
            **InvitationResponse.model_validate(invitation).model_dump(),
            invitation_token=token,
        )

    @app.get("/v1/invitations", response_model=list[InvitationResponse])
    def list_invitations(
        principal: Principal = Depends(require("credential:write")),
        db: Session = Depends(get_db),
    ) -> list[Invitation]:
        return list(
            db.scalars(
                select(Invitation)
                .where(Invitation.organization_id == principal.organization.id)
                .order_by(Invitation.created_at.desc())
            )
        )

    @app.delete("/v1/invitations/{invitation_id}", status_code=204)
    def revoke_invitation(
        invitation_id: str,
        principal: Principal = Depends(require("credential:write")),
        db: Session = Depends(get_db),
    ) -> None:
        invitation = _tenant_get(
            db, Invitation, invitation_id, principal.organization.id
        )
        if invitation.accepted_at is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Accepted invitation cannot be revoked"
            )
        invitation.revoked_at = datetime.now(timezone.utc)
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="invitation.revoke",
            entity_type="invitation",
            entity_id=invitation.id,
        )
        db.commit()

    @app.post(
        "/v1/invitations/accept",
        response_model=TokenResponse,
        tags=["authentication"],
    )
    def accept_invitation(
        payload: InvitationAccept,
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> TokenResponse:
        invitation = db.scalar(
            select(Invitation).where(
                Invitation.token_hash
                == hash_token(payload.token, settings_value.token_pepper)
            )
        )
        now = datetime.now(timezone.utc)
        if (
            invitation is None
            or invitation.accepted_at is not None
            or invitation.revoked_at is not None
            or _aware(invitation.expires_at) <= now
        ):
            raise HTTPException(
                status.HTTP_410_GONE, "Invitation is invalid or expired"
            )
        user = db.scalar(select(User).where(User.email == invitation.email))
        if user is None:
            user = User(
                email=invitation.email,
                display_name=payload.display_name,
                password_hash=hash_password(payload.password),
            )
            db.add(user)
            db.flush()
        membership = Membership(
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=invitation.role,
        )
        db.add(membership)
        invitation.accepted_at = now
        token, credential = _issue_credential(
            db,
            organization_id=invitation.organization_id,
            user_id=user.id,
            kind="session",
            name="invitation",
            expires_at=expires_in(minutes=settings_value.token_ttl_minutes),
            settings=settings_value,
        )
        append_audit_event(
            db,
            organization_id=invitation.organization_id,
            actor_user_id=user.id,
            action="invitation.accept",
            entity_type="invitation",
            entity_id=invitation.id,
        )
        db.commit()
        return TokenResponse(
            access_token=token,
            expires_at=credential.expires_at,
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=membership.role,
        )

    @app.post(
        "/v1/auth/mfa/setup",
        response_model=MfaSetupResponse,
        tags=["authentication"],
    )
    def setup_mfa(
        principal: Principal = Depends(current_principal),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> MfaSetupResponse:
        existing = db.get(UserMfa, principal.user.id)
        if existing and existing.enabled_at:
            raise HTTPException(status.HTTP_409_CONFLICT, "MFA is already enabled")
        secret = new_totp_secret()
        if existing is None:
            existing = UserMfa(
                user_id=principal.user.id,
                secret_ciphertext=seal_mfa_secret(secret, settings_value),
            )
            db.add(existing)
        else:
            existing.secret_ciphertext = seal_mfa_secret(secret, settings_value)
            existing.recovery_code_hashes = []
        db.commit()
        label = quote(
            f"{principal.organization.slug}:{principal.user.email}", safe=""
        )
        issuer = quote("AIx Open", safe="")
        return MfaSetupResponse(
            secret=secret,
            otpauth_uri=(
                f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
                "&algorithm=SHA1&digits=6&period=30"
            ),
        )

    @app.post(
        "/v1/auth/mfa/enable",
        response_model=MfaEnableResponse,
        tags=["authentication"],
    )
    def enable_mfa(
        payload: MfaCodeRequest,
        principal: Principal = Depends(current_principal),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> MfaEnableResponse:
        record = db.get(UserMfa, principal.user.id)
        if record is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "MFA setup is required")
        secret = unseal_mfa_secret(record.secret_ciphertext, settings_value)
        if not verify_totp(secret, payload.code):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid MFA code")
        recovery_codes = new_recovery_codes()
        record.recovery_code_hashes = [
            hash_token(code, settings_value.token_pepper)
            for code in recovery_codes
        ]
        record.enabled_at = datetime.now(timezone.utc)
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="authentication.mfa_enable",
            entity_type="user",
            entity_id=principal.user.id,
        )
        db.commit()
        return MfaEnableResponse(recovery_codes=recovery_codes)

    @app.delete("/v1/auth/mfa", status_code=204, tags=["authentication"])
    def disable_mfa(
        payload: MfaCodeRequest,
        principal: Principal = Depends(current_principal),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> None:
        if principal.organization.require_mfa:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "MFA cannot be disabled while required by the organization",
            )
        if not verify_mfa_code(
            db,
            user_id=principal.user.id,
            code=payload.code,
            settings=settings_value,
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid MFA code")
        db.delete(db.get(UserMfa, principal.user.id))
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="authentication.mfa_disable",
            entity_type="user",
            entity_id=principal.user.id,
        )
        db.commit()

    @app.patch(
        "/v1/organization/security",
        response_model=OrganizationResponse,
        tags=["authentication"],
    )
    def update_organization_security(
        payload: OrganizationSecurityUpdate,
        principal: Principal = Depends(require("credential:write")),
        db: Session = Depends(get_db),
    ) -> Organization:
        if payload.require_mfa:
            unenrolled = db.scalar(
                select(func.count())
                .select_from(Membership)
                .join(User, User.id == Membership.user_id)
                .outerjoin(UserMfa, UserMfa.user_id == User.id)
                .where(
                    Membership.organization_id == principal.organization.id,
                    Membership.active.is_(True),
                    User.active.is_(True),
                    UserMfa.enabled_at.is_(None),
                )
            )
            if unenrolled:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "All active members must enroll in MFA before enforcement",
                )
        principal.organization.require_mfa = payload.require_mfa
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="organization.security_update",
            entity_type="organization",
            entity_id=principal.organization.id,
            payload={"require_mfa": payload.require_mfa},
        )
        db.commit()
        return principal.organization

    @app.post("/v1/api-keys", response_model=TokenResponse, tags=["authentication"])
    def create_api_key(
        payload: ApiKeyRequest,
        principal: Principal = Depends(require("credential:write")),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> TokenResponse:
        days = payload.expires_in_days or settings_value.api_key_ttl_days
        token, credential = _issue_credential(
            db,
            organization_id=principal.organization.id,
            user_id=principal.user.id,
            kind="api_key",
            name=payload.name,
            expires_at=expires_in(days=days),
            settings=settings_value,
        )
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="credential.create",
            entity_type="credential",
            entity_id=credential.id,
            payload={"kind": "api_key", "name": payload.name},
        )
        db.commit()
        return TokenResponse(
            access_token=token,
            expires_at=credential.expires_at,
            organization_id=principal.organization.id,
            user_id=principal.user.id,
            role=principal.role,
        )

    @app.post(
        "/v1/scim-tokens",
        response_model=TokenResponse,
        tags=["authentication"],
    )
    def create_scim_token(
        payload: ScimTokenRequest,
        principal: Principal = Depends(require("credential:write")),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> TokenResponse:
        token, credential = _issue_credential(
            db,
            organization_id=principal.organization.id,
            user_id=principal.user.id,
            kind="scim",
            name=payload.name,
            expires_at=expires_in(days=payload.expires_in_days),
            settings=settings_value,
        )
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="credential.scim_create",
            entity_type="credential",
            entity_id=credential.id,
            payload={"name": payload.name},
        )
        db.commit()
        return TokenResponse(
            access_token=token,
            expires_at=credential.expires_at,
            organization_id=principal.organization.id,
            user_id=principal.user.id,
            role=principal.role,
        )

    @app.get("/scim/v2/ServiceProviderConfig", tags=["scim"])
    def scim_service_provider_config() -> dict[str, Any]:
        return {
            "schemas": [
                "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
            ],
            "patch": {"supported": True},
            "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
            "filter": {"supported": True, "maxResults": 200},
            "changePassword": {"supported": False},
            "sort": {"supported": False},
            "etag": {"supported": False},
            "authenticationSchemes": [
                {
                    "type": "oauthbearertoken",
                    "name": "Bearer Token",
                    "description": "AIx organization SCIM token",
                    "specUri": "https://www.rfc-editor.org/rfc/rfc6750",
                    "primary": True,
                }
            ],
        }

    @app.get("/scim/v2/Users", tags=["scim"])
    def scim_list_users(
        filter: str | None = None,
        startIndex: int = 1,
        count: int = 100,
        principal: Principal = Depends(_scim_principal),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        query = (
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == principal.organization.id)
            .order_by(User.email)
        )
        if filter:
            parts = filter.split(" eq ", 1)
            if len(parts) != 2 or parts[0] not in {"userName", "externalId"}:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "Unsupported SCIM filter"
                )
            value = parts[1].strip().strip('"')
            query = query.where(
                User.email == value.lower()
                if parts[0] == "userName"
                else Membership.scim_external_id == value
            )
        all_rows = list(db.execute(query))
        page = all_rows[max(0, startIndex - 1) : max(0, startIndex - 1) + min(count, 200)]
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": len(all_rows),
            "startIndex": startIndex,
            "itemsPerPage": len(page),
            "Resources": [_scim_user(user, membership) for user, membership in page],
        }

    @app.post("/scim/v2/Users", status_code=201, tags=["scim"])
    def scim_create_user(
        payload: ScimUserCreate,
        principal: Principal = Depends(_scim_principal),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        email = payload.userName.lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                display_name=payload.displayName or email,
                password_hash=hash_password(new_token("scim")),
            )
            db.add(user)
            db.flush()
        if db.scalar(
            select(Membership).where(
                Membership.organization_id == principal.organization.id,
                Membership.user_id == user.id,
            )
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "SCIM user already exists")
        membership = Membership(
            organization_id=principal.organization.id,
            user_id=user.id,
            role=_scim_role(payload.roles),
            active=payload.active,
            scim_external_id=payload.externalId,
        )
        db.add(membership)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="scim.user_create",
            entity_type="membership",
            entity_id=membership.id,
            payload={"user_id": user.id, "external_id": payload.externalId},
        )
        db.commit()
        return _scim_user(user, membership)

    @app.get("/scim/v2/Users/{user_id}", tags=["scim"])
    def scim_get_user(
        user_id: str,
        principal: Principal = Depends(_scim_principal),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        row = db.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == user_id,
                Membership.organization_id == principal.organization.id,
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "SCIM user not found")
        return _scim_user(*row)

    @app.patch("/scim/v2/Users/{user_id}", tags=["scim"])
    def scim_patch_user(
        user_id: str,
        payload: ScimPatchRequest,
        principal: Principal = Depends(_scim_principal),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        row = db.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == user_id,
                Membership.organization_id == principal.organization.id,
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "SCIM user not found")
        user, membership = row
        for operation in payload.Operations:
            path = (operation.path or "").lower()
            if path == "active":
                membership.active = bool(operation.value)
            elif path in {"displayname", "name.formatted"}:
                user.display_name = str(operation.value)
            elif path == "externalid":
                membership.scim_external_id = (
                    None if operation.op == "remove" else str(operation.value)
                )
            elif path == "roles":
                roles = operation.value if isinstance(operation.value, list) else []
                role = _scim_role(roles)
                if membership.role == "owner" and role != "owner" and _active_owner_count(
                    db, principal.organization.id
                ) <= 1:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        "Organization must retain at least one active owner",
                    )
                membership.role = role
            else:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"Unsupported SCIM path: {operation.path}"
                )
        if not membership.active:
            now = datetime.now(timezone.utc)
            for credential in db.scalars(
                select(Credential).where(
                    Credential.organization_id == principal.organization.id,
                    Credential.user_id == user.id,
                    Credential.revoked_at.is_(None),
                )
            ):
                credential.revoked_at = now
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="scim.user_update",
            entity_type="membership",
            entity_id=membership.id,
        )
        db.commit()
        return _scim_user(user, membership)

    @app.delete("/scim/v2/Users/{user_id}", status_code=204, tags=["scim"])
    def scim_delete_user(
        user_id: str,
        principal: Principal = Depends(_scim_principal),
        db: Session = Depends(get_db),
    ) -> None:
        membership = db.scalar(
            select(Membership).where(
                Membership.organization_id == principal.organization.id,
                Membership.user_id == user_id,
            )
        )
        if membership is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "SCIM user not found")
        if membership.role == "owner" and _active_owner_count(
            db, principal.organization.id
        ) <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Organization must retain at least one active owner",
            )
        membership.active = False
        now = datetime.now(timezone.utc)
        for credential in db.scalars(
            select(Credential).where(
                Credential.organization_id == principal.organization.id,
                Credential.user_id == user_id,
                Credential.revoked_at.is_(None),
            )
        ):
            credential.revoked_at = now
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="scim.user_delete",
            entity_type="membership",
            entity_id=membership.id,
        )
        db.commit()

    @app.delete("/v1/credentials/{credential_id}", status_code=204)
    def revoke_credential(
        credential_id: str,
        principal: Principal = Depends(require("credential:write")),
        db: Session = Depends(get_db),
    ) -> None:
        credential = _tenant_get(
            db, Credential, credential_id, principal.organization.id
        )
        credential.revoked_at = datetime.now(timezone.utc)
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="credential.revoke",
            entity_type="credential",
            entity_id=credential.id,
        )
        db.commit()

    @app.post("/v1/systems", response_model=SystemResponse, status_code=201)
    def create_system(
        payload: SystemCreate,
        principal: Principal = Depends(require("system:write")),
        db: Session = Depends(get_db),
    ) -> SystemRecord:
        record = SystemRecord(
            organization_id=principal.organization.id,
            name=payload.name,
            kind=payload.kind,
            description=payload.description,
            metadata_json=payload.metadata,
            created_by=principal.user.id,
        )
        db.add(record)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="system.create",
            entity_type="system",
            entity_id=record.id,
        )
        db.commit()
        return record

    @app.get("/v1/systems", response_model=list[SystemResponse])
    def list_systems(
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> list[SystemRecord]:
        return list(
            db.scalars(
                select(SystemRecord)
                .where(SystemRecord.organization_id == principal.organization.id)
                .order_by(SystemRecord.name)
            )
        )

    @app.post("/v1/rubrics", response_model=RubricResponse, status_code=201)
    def create_rubric(
        payload: RubricCreate,
        principal: Principal = Depends(require("rubric:write")),
        db: Session = Depends(get_db),
    ) -> RubricVersion:
        record = RubricVersion(
            organization_id=principal.organization.id,
            slug=payload.slug,
            version=payload.version,
            content_json=payload.content,
            content_sha256=content_hash(payload.content),
            created_by=principal.user.id,
        )
        db.add(record)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="rubric.create",
            entity_type="rubric_version",
            entity_id=record.id,
        )
        db.commit()
        return record

    @app.post("/v1/rubrics/{rubric_id}/publish", response_model=RubricResponse)
    def publish_rubric(
        rubric_id: str,
        principal: Principal = Depends(require("rubric:write")),
        db: Session = Depends(get_db),
    ) -> RubricVersion:
        rubric = _tenant_get(db, RubricVersion, rubric_id, principal.organization.id)
        if rubric.status != "draft":
            raise HTTPException(status.HTTP_409_CONFLICT, "Rubric is already published")
        rubric.status = "published"
        rubric.published_at = datetime.now(timezone.utc)
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="rubric.publish",
            entity_type="rubric_version",
            entity_id=rubric.id,
            payload={"content_sha256": rubric.content_sha256},
        )
        db.commit()
        return rubric

    @app.get("/v1/rubrics", response_model=list[RubricResponse])
    def list_rubrics(
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> list[RubricVersion]:
        return list(
            db.scalars(
                select(RubricVersion)
                .where(RubricVersion.organization_id == principal.organization.id)
                .order_by(RubricVersion.slug, RubricVersion.created_at.desc())
            )
        )

    @app.post("/v1/assessments", response_model=AssessmentResponse, status_code=201)
    def create_assessment(
        payload: AssessmentCreate,
        principal: Principal = Depends(require("assessment:write")),
        db: Session = Depends(get_db),
    ) -> Assessment:
        _tenant_get(db, SystemRecord, payload.system_id, principal.organization.id)
        if payload.rubric_version_id:
            rubric = _tenant_get(
                db, RubricVersion, payload.rubric_version_id, principal.organization.id
            )
            if rubric.status != "published":
                raise HTTPException(status.HTTP_409_CONFLICT, "Rubric must be published")
        previous = None
        if payload.previous_version_id:
            previous = _tenant_get(
                db, Assessment, payload.previous_version_id, principal.organization.id
            )
            if previous.system_id != payload.system_id:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Previous assessment belongs to another system",
                )
        validate_assessment(payload.assessment)
        current_version = db.scalar(
            select(func.max(Assessment.version)).where(
                Assessment.organization_id == principal.organization.id,
                Assessment.system_id == payload.system_id,
            )
        )
        record = Assessment(
            organization_id=principal.organization.id,
            system_id=payload.system_id,
            rubric_version_id=payload.rubric_version_id,
            previous_version_id=previous.id if previous else None,
            version=(current_version or 0) + 1,
            input_json=payload.assessment,
            created_by=principal.user.id,
        )
        db.add(record)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="assessment.create",
            entity_type="assessment",
            entity_id=record.id,
            payload={"version": record.version},
        )
        db.commit()
        return record

    @app.put("/v1/assessments/{assessment_id}", response_model=AssessmentResponse)
    def update_assessment(
        assessment_id: str,
        payload: AssessmentUpdate,
        principal: Principal = Depends(require("assessment:write")),
        db: Session = Depends(get_db),
    ) -> Assessment:
        record = _tenant_get(db, Assessment, assessment_id, principal.organization.id)
        if record.status != "draft":
            raise HTTPException(status.HTTP_409_CONFLICT, "Only drafts can be edited")
        validate_assessment(payload.assessment)
        record.input_json = payload.assessment
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="assessment.update",
            entity_type="assessment",
            entity_id=record.id,
        )
        db.commit()
        return record

    @app.get("/v1/assessments", response_model=list[AssessmentResponse])
    def list_assessments(
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> list[Assessment]:
        return list(
            db.scalars(
                select(Assessment)
                .where(Assessment.organization_id == principal.organization.id)
                .order_by(Assessment.created_at.desc())
            )
        )

    @app.get(
        "/v1/assessment-comparisons",
        response_model=AssessmentComparisonResponse,
    )
    def compare_assessments(
        baseline_id: str,
        candidate_id: str,
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> AssessmentComparisonResponse:
        baseline = _tenant_get(
            db, Assessment, baseline_id, principal.organization.id
        )
        candidate = _tenant_get(
            db, Assessment, candidate_id, principal.organization.id
        )
        if baseline.system_id != candidate.system_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Assessments must belong to the same system",
            )
        if not baseline.result_json or not candidate.result_json:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Only finalized assessments can be compared",
            )
        baseline_domains = baseline.result_json["domain_scores"]
        candidate_domains = candidate.result_json["domain_scores"]
        return AssessmentComparisonResponse(
            baseline_id=baseline.id,
            candidate_id=candidate.id,
            baseline_version=baseline.version,
            candidate_version=candidate.version,
            adjusted_score_delta=(
                candidate.result_json["adjusted_score"]
                - baseline.result_json["adjusted_score"]
            ),
            confidence_delta=(
                candidate.result_json["confidence"]
                - baseline.result_json["confidence"]
            ),
            evidence_quality_delta=(
                candidate.result_json["evidence_quality"]
                - baseline.result_json["evidence_quality"]
            ),
            constraint_skew_delta=(
                candidate.result_json["constraint_skew"]
                - baseline.result_json["constraint_skew"]
            ),
            domain_score_deltas={
                domain: candidate_domains[domain] - baseline_domains[domain]
                for domain in baseline_domains
            },
        )

    @app.get("/v1/assessments/{assessment_id}", response_model=AssessmentResponse)
    def get_assessment(
        assessment_id: str,
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> Assessment:
        return _tenant_get(db, Assessment, assessment_id, principal.organization.id)

    def transition(
        *,
        db: Session,
        principal: Principal,
        assessment_id: str,
        expected: str,
        target: str,
        action: str,
    ) -> Assessment:
        record = _tenant_get(db, Assessment, assessment_id, principal.organization.id)
        if record.status != expected:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Assessment must be {expected} to become {target}",
            )
        record.status = target
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action=action,
            entity_type="assessment",
            entity_id=record.id,
        )
        db.commit()
        return record

    @app.post("/v1/assessments/{assessment_id}/submit", response_model=AssessmentResponse)
    def submit_assessment(
        assessment_id: str,
        principal: Principal = Depends(require("assessment:write")),
        db: Session = Depends(get_db),
    ) -> Assessment:
        return transition(
            db=db,
            principal=principal,
            assessment_id=assessment_id,
            expected="draft",
            target="in_review",
            action="assessment.submit",
        )

    @app.post("/v1/assessments/{assessment_id}/approve", response_model=AssessmentResponse)
    def approve_assessment(
        assessment_id: str,
        principal: Principal = Depends(require("assessment:approve")),
        db: Session = Depends(get_db),
    ) -> Assessment:
        return transition(
            db=db,
            principal=principal,
            assessment_id=assessment_id,
            expected="in_review",
            target="approved",
            action="assessment.approve",
        )

    @app.post("/v1/assessments/{assessment_id}/reject", response_model=AssessmentResponse)
    def reject_assessment(
        assessment_id: str,
        principal: Principal = Depends(require("assessment:review")),
        db: Session = Depends(get_db),
    ) -> Assessment:
        return transition(
            db=db,
            principal=principal,
            assessment_id=assessment_id,
            expected="in_review",
            target="draft",
            action="assessment.reject",
        )

    @app.post("/v1/assessments/{assessment_id}/finalize", response_model=AssessmentResponse)
    def finalize_assessment(
        assessment_id: str,
        principal: Principal = Depends(require("assessment:finalize")),
        db: Session = Depends(get_db),
    ) -> Assessment:
        record = _tenant_get(db, Assessment, assessment_id, principal.organization.id)
        if record.status != "approved":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Assessment must be approved before finalization",
            )
        result = score_assessment(record.input_json).to_dict()
        record.input_sha256 = content_hash(record.input_json)
        record.result_json = result
        record.result_sha256 = content_hash(result)
        record.status = "finalized"
        record.finalized_by = principal.user.id
        record.finalized_at = datetime.now(timezone.utc)
        policies = db.scalars(
            select(Policy).where(
                Policy.organization_id == principal.organization.id,
                Policy.active.is_(True),
            )
        )
        policy_outcomes = []
        for policy in policies:
            decision = evaluate_policy(result, policy.rules_json)
            db.add(
                PolicyDecision(
                    organization_id=principal.organization.id,
                    assessment_id=record.id,
                    policy_id=policy.id,
                    outcome=decision["outcome"],
                    details_json=decision,
                )
            )
            policy_outcomes.append({"policy_id": policy.id, **decision})
        enqueue_webhook_event(
            db,
            organization_id=principal.organization.id,
            event_type="assessment.finalized",
            data={
                "assessment_id": record.id,
                "system_id": record.system_id,
                "version": record.version,
                "result_sha256": record.result_sha256,
                "adjusted_score": result["adjusted_score"],
                "policy_outcomes": policy_outcomes,
            },
        )
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="assessment.finalize",
            entity_type="assessment",
            entity_id=record.id,
            payload={
                "input_sha256": record.input_sha256,
                "result_sha256": record.result_sha256,
                "policy_outcomes": policy_outcomes,
            },
        )
        db.commit()
        return record

    @app.post(
        "/v1/assessments/{assessment_id}/evidence",
        response_model=EvidenceResponse,
        status_code=201,
    )
    def create_evidence(
        assessment_id: str,
        payload: EvidenceCreate,
        principal: Principal = Depends(require("evidence:write")),
        db: Session = Depends(get_db),
    ) -> Evidence:
        assessment = _tenant_get(
            db, Assessment, assessment_id, principal.organization.id
        )
        if assessment.status == "finalized":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Finalized assessment evidence is immutable",
            )
        record = Evidence(
            organization_id=principal.organization.id,
            assessment_id=assessment.id,
            indicator_code=payload.indicator_code,
            source_type=payload.source_type,
            uri=payload.uri,
            object_key=payload.object_key,
            content_sha256=payload.content_sha256.lower(),
            trust_score=payload.trust_score,
            freshness_at=payload.freshness_at,
            classification=payload.classification,
            retention_until=payload.retention_until,
            metadata_json=payload.metadata,
            scan_status="not_required",
            created_by=principal.user.id,
        )
        db.add(record)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="evidence.create",
            entity_type="evidence",
            entity_id=record.id,
            payload={
                "assessment_id": assessment.id,
                "content_sha256": record.content_sha256,
            },
        )
        db.commit()
        return record

    @app.post(
        "/v1/assessments/{assessment_id}/evidence/upload",
        response_model=EvidenceResponse,
        status_code=201,
    )
    def upload_evidence(
        assessment_id: str,
        file: UploadFile = File(...),
        indicator_code: str = Form(..., pattern=r"^(P[1-6]|B[1-6]|C[1-6]|H[1-5]|F[1-6])$"),
        source_type: str = Form(..., min_length=1, max_length=40),
        trust_score: float = Form(..., ge=0, le=1),
        classification: str = Form(default="internal"),
        freshness_at: datetime | None = Form(default=None),
        retention_until: datetime | None = Form(default=None),
        principal: Principal = Depends(require("evidence:write")),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> Evidence:
        assessment = _tenant_get(
            db, Assessment, assessment_id, principal.organization.id
        )
        if assessment.status == "finalized":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Finalized assessment evidence is immutable",
            )
        if classification not in {
            "public",
            "internal",
            "confidential",
            "restricted",
        }:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Invalid evidence classification",
            )
        object_key = evidence_object_key(
            principal.organization.id,
            assessment.id,
            file.filename,
        )
        try:
            stored = store_upload(
                source=file.file,
                store=object_store(settings_value),
                object_key=object_key,
                content_type=file.content_type or "application/octet-stream",
                max_bytes=settings_value.storage_max_bytes,
                settings=settings_value,
            )
        except ValueError as exc:
            code = (
                status.HTTP_422_UNPROCESSABLE_ENTITY
                if "malware" in str(exc).lower()
                else status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )
            raise HTTPException(code, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Evidence malware scanner is unavailable",
            ) from exc
        effective_retention = retention_until or (
            datetime.now(timezone.utc)
            + timedelta(days=settings_value.evidence_retention_days)
        )
        record = Evidence(
            organization_id=principal.organization.id,
            assessment_id=assessment.id,
            indicator_code=indicator_code,
            source_type=source_type,
            uri="pending://evidence-upload",
            object_key=stored.object_key,
            content_sha256=stored.content_sha256,
            trust_score=trust_score,
            freshness_at=freshness_at,
            classification=classification,
            retention_until=effective_retention,
            metadata_json={
                "filename": file.filename,
                "content_type": stored.content_type,
                "size_bytes": stored.size_bytes,
                "storage_backend": settings_value.storage_backend,
            },
            scan_status=(
                "clean" if settings_value.malware_scan_enabled else "not_required"
            ),
            scanned_at=(
                datetime.now(timezone.utc)
                if settings_value.malware_scan_enabled
                else None
            ),
            created_by=principal.user.id,
        )
        db.add(record)
        db.flush()
        record.uri = (
            f"{settings_value.public_base_url}/v1/evidence/{record.id}/content"
        )
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="evidence.upload",
            entity_type="evidence",
            entity_id=record.id,
            payload={
                "assessment_id": assessment.id,
                "content_sha256": stored.content_sha256,
                "size_bytes": stored.size_bytes,
                "classification": classification,
            },
        )
        enqueue_webhook_event(
            db,
            organization_id=principal.organization.id,
            event_type="evidence.uploaded",
            data={
                "evidence_id": record.id,
                "assessment_id": assessment.id,
                "indicator_code": indicator_code,
                "content_sha256": stored.content_sha256,
                "size_bytes": stored.size_bytes,
            },
        )
        db.commit()
        return record

    @app.get("/v1/evidence/{evidence_id}/content")
    def download_evidence(
        evidence_id: str,
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ):
        evidence = _tenant_get(
            db, Evidence, evidence_id, principal.organization.id
        )
        if not evidence.object_key:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Evidence record references an external source",
            )
        try:
            handle = object_store(settings_value).open(evidence.object_key)
        except FileNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Evidence object is unavailable",
            ) from exc
        filename = evidence.metadata_json.get("filename", f"{evidence.id}.bin")
        content_type = evidence.metadata_json.get(
            "content_type", "application/octet-stream"
        )
        return StreamingResponse(
            iter_file(handle),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Content-SHA256": evidence.content_sha256,
            },
        )

    @app.get(
        "/v1/assessments/{assessment_id}/evidence",
        response_model=list[EvidenceResponse],
    )
    def list_evidence(
        assessment_id: str,
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> list[Evidence]:
        _tenant_get(db, Assessment, assessment_id, principal.organization.id)
        return list(
            db.scalars(
                select(Evidence)
                .where(
                    Evidence.organization_id == principal.organization.id,
                    Evidence.assessment_id == assessment_id,
                )
                .order_by(Evidence.created_at)
            )
        )

    @app.post("/v1/policies", response_model=PolicyResponse, status_code=201)
    def create_policy(
        payload: PolicyCreate,
        principal: Principal = Depends(require("policy:write")),
        db: Session = Depends(get_db),
    ) -> Policy:
        record = Policy(
            organization_id=principal.organization.id,
            name=payload.name,
            rules_json=payload.rules,
            active=payload.active,
            created_by=principal.user.id,
        )
        db.add(record)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="policy.create",
            entity_type="policy",
            entity_id=record.id,
        )
        db.commit()
        return record

    @app.get("/v1/policies", response_model=list[PolicyResponse])
    def list_policies(
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> list[Policy]:
        return list(
            db.scalars(
                select(Policy)
                .where(Policy.organization_id == principal.organization.id)
                .order_by(Policy.name)
            )
        )

    @app.get("/v1/audit-events", response_model=list[AuditResponse])
    def list_audit_events(
        principal: Principal = Depends(require("audit:read")),
        db: Session = Depends(get_db),
    ) -> list[AuditEvent]:
        return list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.organization_id == principal.organization.id)
                .order_by(AuditEvent.created_at, AuditEvent.id)
            )
        )

    @app.post("/v1/jobs", response_model=JobResponse, status_code=202)
    def create_job(
        payload: JobCreate,
        principal: Principal = Depends(require("assessment:write")),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> Job:
        existing = db.scalar(
            select(Job).where(
                Job.organization_id == principal.organization.id,
                Job.idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
        assessment_id = payload.payload.get("assessment_id")
        if not isinstance(assessment_id, str):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "assessment_report requires payload.assessment_id",
            )
        assessment = _tenant_get(
            db, Assessment, assessment_id, principal.organization.id
        )
        if assessment.status != "finalized":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Reports can only be generated for finalized assessments",
            )
        output_format = payload.payload.get("format", "markdown")
        if output_format not in {"markdown", "json", "csv", "html"}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Report format must be markdown, json, csv, or html",
            )
        record = Job(
            organization_id=principal.organization.id,
            kind=payload.kind,
            idempotency_key=payload.idempotency_key,
            payload_json={**payload.payload, "format": output_format},
            max_attempts=payload.max_attempts,
            created_by=principal.user.id,
        )
        db.add(record)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="job.create",
            entity_type="job",
            entity_id=record.id,
            payload={"kind": record.kind},
        )
        db.commit()
        try:
            enqueue_job(settings_value, record.id)
        except RedisError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Job queue is unavailable; the durable job will be recovered",
            ) from exc
        return record

    @app.get("/v1/jobs", response_model=list[JobResponse])
    def list_jobs(
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> list[Job]:
        return list(
            db.scalars(
                select(Job)
                .where(Job.organization_id == principal.organization.id)
                .order_by(Job.created_at.desc())
            )
        )

    @app.get("/v1/jobs/{job_id}", response_model=JobResponse)
    def get_job(
        job_id: str,
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> Job:
        return _tenant_get(db, Job, job_id, principal.organization.id)

    @app.post(
        "/v1/webhooks",
        response_model=WebhookCreatedResponse,
        status_code=201,
    )
    def create_webhook(
        payload: WebhookCreate,
        principal: Principal = Depends(require("webhook:write")),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> WebhookCreatedResponse:
        try:
            validate_webhook_url(payload.url, settings_value)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)
            ) from exc
        secret = new_token("aixwh")
        endpoint = WebhookEndpoint(
            organization_id=principal.organization.id,
            url=payload.url,
            events_json=sorted(set(payload.events)),
            secret_ciphertext=seal_secret(secret, settings_value),
            created_by=principal.user.id,
        )
        db.add(endpoint)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="webhook.create",
            entity_type="webhook_endpoint",
            entity_id=endpoint.id,
            payload={"url": endpoint.url, "events": endpoint.events_json},
        )
        db.commit()
        return WebhookCreatedResponse(
            **WebhookResponse.model_validate(endpoint).model_dump(),
            signing_secret=secret,
        )

    @app.get("/v1/webhooks", response_model=list[WebhookResponse])
    def list_webhooks(
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> list[WebhookEndpoint]:
        return list(
            db.scalars(
                select(WebhookEndpoint)
                .where(
                    WebhookEndpoint.organization_id == principal.organization.id
                )
                .order_by(WebhookEndpoint.created_at)
            )
        )

    @app.delete("/v1/webhooks/{endpoint_id}", status_code=204)
    def disable_webhook(
        endpoint_id: str,
        principal: Principal = Depends(require("webhook:write")),
        db: Session = Depends(get_db),
    ) -> None:
        endpoint = _tenant_get(
            db, WebhookEndpoint, endpoint_id, principal.organization.id
        )
        endpoint.active = False
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="webhook.disable",
            entity_type="webhook_endpoint",
            entity_id=endpoint.id,
        )
        db.commit()

    @app.get(
        "/v1/webhook-deliveries",
        response_model=list[WebhookDeliveryResponse],
    )
    def list_webhook_deliveries(
        principal: Principal = Depends(require("read")),
        db: Session = Depends(get_db),
    ) -> list[WebhookDelivery]:
        return list(
            db.scalars(
                select(WebhookDelivery)
                .where(
                    WebhookDelivery.organization_id == principal.organization.id
                )
                .order_by(WebhookDelivery.created_at.desc())
            )
        )

    @app.post("/v1/legal-holds", response_model=LegalHoldResponse, status_code=201)
    def create_legal_hold(
        payload: LegalHoldCreate,
        principal: Principal = Depends(require("privacy:write")),
        db: Session = Depends(get_db),
    ) -> LegalHold:
        if payload.evidence_id:
            _tenant_get(
                db, Evidence, payload.evidence_id, principal.organization.id
            )
        hold = LegalHold(
            organization_id=principal.organization.id,
            evidence_id=payload.evidence_id,
            reason=payload.reason,
            created_by=principal.user.id,
        )
        db.add(hold)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="legal_hold.create",
            entity_type="legal_hold",
            entity_id=hold.id,
            payload={"evidence_id": hold.evidence_id, "reason": hold.reason},
        )
        db.commit()
        return hold

    @app.get("/v1/legal-holds", response_model=list[LegalHoldResponse])
    def list_legal_holds(
        principal: Principal = Depends(require("privacy:write")),
        db: Session = Depends(get_db),
    ) -> list[LegalHold]:
        return list(
            db.scalars(
                select(LegalHold)
                .where(LegalHold.organization_id == principal.organization.id)
                .order_by(LegalHold.created_at.desc())
            )
        )

    @app.post(
        "/v1/legal-holds/{hold_id}/release",
        response_model=LegalHoldResponse,
    )
    def release_legal_hold(
        hold_id: str,
        principal: Principal = Depends(require("privacy:write")),
        db: Session = Depends(get_db),
    ) -> LegalHold:
        hold = _tenant_get(db, LegalHold, hold_id, principal.organization.id)
        if hold.released_at is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Legal hold is already released")
        hold.released_at = datetime.now(timezone.utc)
        hold.released_by = principal.user.id
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="legal_hold.release",
            entity_type="legal_hold",
            entity_id=hold.id,
        )
        db.commit()
        return hold

    @app.post(
        "/v1/privacy/exports",
        response_model=PrivacyRequestResponse,
        status_code=202,
    )
    def request_privacy_export(
        principal: Principal = Depends(require("privacy:write")),
        db: Session = Depends(get_db),
    ) -> PrivacyRequest:
        request = PrivacyRequest(
            organization_id=principal.organization.id,
            requested_by=principal.user.id,
            kind="export",
        )
        db.add(request)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="privacy.export_request",
            entity_type="privacy_request",
            entity_id=request.id,
        )
        db.commit()
        return request

    @app.post(
        "/v1/privacy/deletions",
        response_model=PrivacyRequestResponse,
        status_code=202,
    )
    def request_privacy_deletion(
        payload: PrivacyDeleteRequest,
        principal: Principal = Depends(require("privacy:write")),
        db: Session = Depends(get_db),
        settings_value: Settings = Depends(get_settings),
    ) -> PrivacyRequest:
        expected = f"delete {principal.organization.slug}"
        if payload.confirmation != expected:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Confirmation must exactly equal: {expected}",
            )
        existing = db.scalar(
            select(PrivacyRequest).where(
                PrivacyRequest.organization_id == principal.organization.id,
                PrivacyRequest.kind == "delete",
                PrivacyRequest.status.in_(("pending", "running")),
            )
        )
        if existing:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A deletion request is already active",
            )
        request = PrivacyRequest(
            organization_id=principal.organization.id,
            requested_by=principal.user.id,
            kind="delete",
            confirmation=payload.confirmation,
            scheduled_for=datetime.now(timezone.utc)
            + timedelta(hours=settings_value.privacy_deletion_delay_hours),
        )
        db.add(request)
        db.flush()
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="privacy.deletion_request",
            entity_type="privacy_request",
            entity_id=request.id,
            payload={"scheduled_for": request.scheduled_for.isoformat()},
        )
        db.commit()
        return request

    @app.get(
        "/v1/privacy/requests",
        response_model=list[PrivacyRequestResponse],
    )
    def list_privacy_requests(
        principal: Principal = Depends(require("privacy:write")),
        db: Session = Depends(get_db),
    ) -> list[PrivacyRequest]:
        return list(
            db.scalars(
                select(PrivacyRequest)
                .where(
                    PrivacyRequest.organization_id == principal.organization.id
                )
                .order_by(PrivacyRequest.created_at.desc())
            )
        )

    @app.post(
        "/v1/privacy/requests/{request_id}/cancel",
        response_model=PrivacyRequestResponse,
    )
    def cancel_privacy_request(
        request_id: str,
        principal: Principal = Depends(require("privacy:write")),
        db: Session = Depends(get_db),
    ) -> PrivacyRequest:
        request = _tenant_get(
            db, PrivacyRequest, request_id, principal.organization.id
        )
        if request.status != "pending":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Only pending privacy requests can be cancelled",
            )
        request.status = "cancelled"
        append_audit_event(
            db,
            organization_id=principal.organization.id,
            actor_user_id=principal.user.id,
            action="privacy.request_cancel",
            entity_type="privacy_request",
            entity_id=request.id,
        )
        db.commit()
        return request

    return app
