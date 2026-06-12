from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

from fastapi.testclient import TestClient
from fastapi.responses import RedirectResponse
import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from aix_platform.app import create_app
from aix_platform.audit import verify_audit_chain
from aix_platform.config import Settings, get_settings
from aix_platform.database import Base, get_db
from aix_platform.orm import (
    AuditEvent,
    Credential,
    Membership,
    Organization,
    PolicyDecision,
    User,
)
from aix_platform.privacy import process_next_privacy_request, purge_expired_evidence
from aix_platform.security import (
    expires_in,
    hash_password,
    hash_token,
    new_token,
    totp_code,
)
from aix_platform.webhooks import deliver_next_webhook
from aix_platform.worker import process_next_job


@pytest.fixture
def platform(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite://",
        token_pepper="test-token-pepper-value",
        token_ttl_minutes=60,
        storage_path=tmp_path / "evidence",
        webhook_secret_pepper="test-webhook-secret-pepper",
    )
    app = create_app(settings=settings, create_schema=False)

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, session_factory, settings
    engine.dispose()


def _bootstrap(client: TestClient) -> dict:
    response = client.post(
        "/v1/bootstrap",
        json={
            "organization_name": "AIx Research",
            "organization_slug": "aix-research",
            "email": "owner@example.com",
            "display_name": "Owner",
            "password": "a-long-test-password",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_full_assessment_workflow(platform, example_assessment):
    client, session_factory, _ = platform
    auth = _bootstrap(client)
    headers = _headers(auth["access_token"])

    me = client.get("/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "owner"

    system = client.post(
        "/v1/systems",
        headers=headers,
        json={
            "name": "Customer Support Model",
            "kind": "ai_system",
            "description": "Production support assistant",
            "metadata": {"owner": "support"},
        },
    )
    assert system.status_code == 201, system.text
    system_id = system.json()["id"]

    policy = client.post(
        "/v1/policies",
        headers=headers,
        json={
            "name": "production-release",
            "rules": {
                "minimum_adjusted_score": 99,
                "minimum_confidence": 0.5,
                "domain_minimums": {"P": 30, "B": 30},
            },
        },
    )
    assert policy.status_code == 201, policy.text

    assessment = client.post(
        "/v1/assessments",
        headers=headers,
        json={"system_id": system_id, "assessment": example_assessment},
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["id"]
    assert assessment.json()["version"] == 1

    file_content = b"auditable evidence payload"
    uploaded = client.post(
        f"/v1/assessments/{assessment_id}/evidence/upload",
        headers={"Authorization": headers["Authorization"]},
        data={
            "indicator_code": "P1",
            "source_type": "audit",
            "trust_score": "0.95",
            "classification": "confidential",
        },
        files={"file": ("factuality.txt", file_content, "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    uploaded_body = uploaded.json()
    assert uploaded_body["content_sha256"] == sha256(file_content).hexdigest()
    assert uploaded_body["metadata_json"]["size_bytes"] == len(file_content)
    downloaded = client.get(
        f"/v1/evidence/{uploaded_body['id']}/content", headers=headers
    )
    assert downloaded.status_code == 200
    assert downloaded.content == file_content
    assert downloaded.headers["x-content-sha256"] == sha256(file_content).hexdigest()

    evidence = client.post(
        f"/v1/assessments/{assessment_id}/evidence",
        headers=headers,
        json={
            "indicator_code": "P1",
            "source_type": "audit",
            "uri": "https://evidence.example/audit/1",
            "content_sha256": "a" * 64,
            "trust_score": 0.9,
            "classification": "confidential",
            "metadata": {"reviewer": "external"},
        },
    )
    assert evidence.status_code == 201, evidence.text

    assert (
        client.post(f"/v1/assessments/{assessment_id}/submit", headers=headers).json()[
            "status"
        ]
        == "in_review"
    )
    assert (
        client.post(f"/v1/assessments/{assessment_id}/reject", headers=headers).json()[
            "status"
        ]
        == "draft"
    )
    client.post(f"/v1/assessments/{assessment_id}/submit", headers=headers)
    assert (
        client.post(f"/v1/assessments/{assessment_id}/approve", headers=headers).json()[
            "status"
        ]
        == "approved"
    )
    finalized = client.post(
        f"/v1/assessments/{assessment_id}/finalize", headers=headers
    )
    assert finalized.status_code == 200, finalized.text
    body = finalized.json()
    assert body["status"] == "finalized"
    assert len(body["input_sha256"]) == 64
    assert len(body["result_sha256"]) == 64
    assert body["result_json"]["domain_scores"]

    candidate = client.post(
        "/v1/assessments",
        headers=headers,
        json={
            "system_id": system_id,
            "previous_version_id": assessment_id,
            "assessment": example_assessment,
        },
    ).json()
    client.post(f"/v1/assessments/{candidate['id']}/submit", headers=headers)
    client.post(f"/v1/assessments/{candidate['id']}/approve", headers=headers)
    client.post(f"/v1/assessments/{candidate['id']}/finalize", headers=headers)
    comparison = client.get(
        "/v1/assessment-comparisons",
        headers=headers,
        params={"baseline_id": assessment_id, "candidate_id": candidate["id"]},
    )
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["candidate_version"] == 2
    assert comparison.json()["adjusted_score_delta"] == 0

    queued = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "kind": "assessment_report",
            "idempotency_key": "report-test-0001",
            "payload": {"assessment_id": assessment_id, "format": "markdown"},
        },
    )
    assert queued.status_code == 202, queued.text
    job_id = queued.json()["id"]
    duplicate = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "kind": "assessment_report",
            "idempotency_key": "report-test-0001",
            "payload": {"assessment_id": assessment_id, "format": "markdown"},
        },
    )
    assert duplicate.json()["id"] == job_id
    with session_factory() as db:
        processed = process_next_job(db)
        assert processed is not None
        assert processed.status == "succeeded"
        assert processed.result_json["content"].startswith("# AIx Report:")
    assert client.get(f"/v1/jobs/{job_id}", headers=headers).json()["status"] == "succeeded"

    update = client.put(
        f"/v1/assessments/{assessment_id}",
        headers=headers,
        json={"assessment": example_assessment},
    )
    assert update.status_code == 409
    assert update.json()["error"]["code"] == "http_409"

    late_evidence = client.post(
        f"/v1/assessments/{assessment_id}/evidence",
        headers=headers,
        json={
            "indicator_code": "P1",
            "source_type": "audit",
            "uri": "https://evidence.example/late",
            "content_sha256": "b" * 64,
            "trust_score": 0.8,
        },
    )
    assert late_evidence.status_code == 409

    with session_factory() as db:
        decision = db.scalar(
            select(PolicyDecision).where(
                PolicyDecision.assessment_id == assessment_id
            )
        )
        assert decision is not None
        assert decision.outcome == "fail"
        events = list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.organization_id == auth["organization_id"])
                .order_by(AuditEvent.created_at, AuditEvent.id)
            )
        )
        assert verify_audit_chain(events)
        assert events[-1].action == "job.succeed"


def test_tenant_isolation_and_revocation(platform):
    client, session_factory, settings = platform
    first = _bootstrap(client)
    first_headers = _headers(first["access_token"])
    first_system = client.post(
        "/v1/systems",
        headers=first_headers,
        json={"name": "Tenant One System", "kind": "ai_system"},
    ).json()

    with session_factory() as db:
        second_org = Organization(name="Second Tenant", slug="second-tenant")
        second_user = User(
            email="second@example.com",
            display_name="Second Owner",
            password_hash=hash_password("another-long-password"),
        )
        db.add_all([second_org, second_user])
        db.flush()
        db.add(
            Membership(
                organization_id=second_org.id,
                user_id=second_user.id,
                role="owner",
            )
        )
        token = new_token("aixs")
        credential = Credential(
            organization_id=second_org.id,
            user_id=second_user.id,
            kind="session",
            name="test",
            token_hash=hash_token(token, settings.token_pepper),
            expires_at=expires_in(minutes=60),
        )
        db.add(credential)
        db.commit()
        credential_id = credential.id

    second_headers = _headers(token)
    systems = client.get("/v1/systems", headers=second_headers)
    assert systems.status_code == 200
    assert systems.json() == []
    hidden = client.get(
        f"/v1/assessments/{first_system['id']}", headers=second_headers
    )
    assert hidden.status_code == 404

    revoke = client.delete(
        f"/v1/credentials/{credential_id}", headers=second_headers
    )
    assert revoke.status_code == 204
    assert client.get("/v1/me", headers=second_headers).status_code == 401


def test_member_roles_are_enforced(platform):
    client, _, _ = platform
    owner = _bootstrap(client)
    owner_headers = _headers(owner["access_token"])
    member = client.post(
        "/v1/members",
        headers=owner_headers,
        json={
            "email": "viewer@example.com",
            "display_name": "Read Only",
            "role": "viewer",
            "password": "viewer-long-password",
        },
    )
    assert member.status_code == 201, member.text
    login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "aix-research",
            "email": "viewer@example.com",
            "password": "viewer-long-password",
        },
    )
    viewer_headers = _headers(login.json()["access_token"])
    assert client.get("/v1/systems", headers=viewer_headers).status_code == 200
    denied = client.post(
        "/v1/systems",
        headers=viewer_headers,
        json={"name": "Forbidden", "kind": "ai_system"},
    )
    assert denied.status_code == 403


def test_invitations_role_management_and_owner_protection(platform):
    client, _, _ = platform
    owner = _bootstrap(client)
    headers = _headers(owner["access_token"])

    invited = client.post(
        "/v1/invitations",
        headers=headers,
        json={"email": "invited@example.com", "role": "reviewer"},
    )
    assert invited.status_code == 201, invited.text
    invitation = invited.json()
    accepted = client.post(
        "/v1/invitations/accept",
        json={
            "token": invitation["invitation_token"],
            "display_name": "Invited Reviewer",
            "password": "invited-long-password",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role"] == "reviewer"
    assert (
        client.post(
            "/v1/invitations/accept",
            json={
                "token": invitation["invitation_token"],
                "display_name": "Again",
                "password": "another-long-password",
            },
        ).status_code
        == 410
    )

    member_id = accepted.json()["user_id"]
    updated = client.patch(
        f"/v1/members/{member_id}",
        headers=headers,
        json={"role": "viewer", "active": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["role"] == "viewer"
    assert updated.json()["active"] is False
    assert (
        client.get(
            "/v1/me", headers=_headers(accepted.json()["access_token"])
        ).status_code
        == 401
    )
    owner_update = client.patch(
        f"/v1/members/{owner['user_id']}",
        headers=headers,
        json={"role": "admin"},
    )
    assert owner_update.status_code == 409


def test_mfa_login_and_organization_enforcement(platform):
    client, _, _ = platform
    owner = _bootstrap(client)
    headers = _headers(owner["access_token"])
    setup = client.post("/v1/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enabled = client.post(
        "/v1/auth/mfa/enable",
        headers=headers,
        json={"code": totp_code(secret)},
    )
    assert enabled.status_code == 200, enabled.text
    recovery_code = enabled.json()["recovery_codes"][0]

    missing = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "aix-research",
            "email": "owner@example.com",
            "password": "a-long-test-password",
        },
    )
    assert missing.status_code == 401
    login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "aix-research",
            "email": "owner@example.com",
            "password": "a-long-test-password",
            "mfa_code": totp_code(secret),
        },
    )
    assert login.status_code == 200, login.text
    recovery_login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "aix-research",
            "email": "owner@example.com",
            "password": "a-long-test-password",
            "mfa_code": recovery_code,
        },
    )
    assert recovery_login.status_code == 200
    assert (
        client.post(
            "/v1/auth/login",
            json={
                "organization_slug": "aix-research",
                "email": "owner@example.com",
                "password": "a-long-test-password",
                "mfa_code": recovery_code,
            },
        ).status_code
        == 401
    )
    enforcement = client.patch(
        "/v1/organization/security",
        headers=headers,
        json={"require_mfa": True},
    )
    assert enforcement.status_code == 200, enforcement.text
    assert enforcement.json()["require_mfa"] is True


def test_scim_provisioning_requires_dedicated_token(platform):
    client, _, _ = platform
    owner = _bootstrap(client)
    owner_headers = _headers(owner["access_token"])
    denied = client.get("/scim/v2/Users", headers=owner_headers)
    assert denied.status_code == 403

    token_response = client.post(
        "/v1/scim-tokens",
        headers=owner_headers,
        json={"name": "identity-provider"},
    )
    assert token_response.status_code == 200, token_response.text
    scim_headers = _headers(token_response.json()["access_token"])
    created = client.post(
        "/scim/v2/Users",
        headers=scim_headers,
        json={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "provisioned@example.com",
            "externalId": "idp-123",
            "displayName": "Provisioned User",
            "roles": [{"value": "assessor"}],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["externalId"] == "idp-123"
    assert body["roles"][0]["value"] == "assessor"

    listed = client.get(
        "/scim/v2/Users",
        headers=scim_headers,
        params={"filter": 'externalId eq "idp-123"'},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["totalResults"] == 1
    patched = client.patch(
        f"/scim/v2/Users/{body['id']}",
        headers=scim_headers,
        json={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "active", "value": False}
            ],
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["active"] is False


def test_legal_hold_blocks_retention_purge(platform, example_assessment):
    client, session_factory, settings = platform
    owner = _bootstrap(client)
    headers = _headers(owner["access_token"])
    system = client.post(
        "/v1/systems",
        headers=headers,
        json={"name": "Held Evidence System", "kind": "ai_system"},
    ).json()
    assessment = client.post(
        "/v1/assessments",
        headers=headers,
        json={"system_id": system["id"], "assessment": example_assessment},
    ).json()
    evidence = client.post(
        f"/v1/assessments/{assessment['id']}/evidence",
        headers=headers,
        json={
            "indicator_code": "P1",
            "source_type": "audit",
            "uri": "https://evidence.example/held",
            "content_sha256": "c" * 64,
            "trust_score": 0.8,
            "retention_until": "2000-01-01T00:00:00Z",
        },
    ).json()
    hold = client.post(
        "/v1/legal-holds",
        headers=headers,
        json={"evidence_id": evidence["id"], "reason": "Pending litigation"},
    )
    assert hold.status_code == 201, hold.text
    with session_factory() as db:
        assert purge_expired_evidence(db, settings) == 0
    released = client.post(
        f"/v1/legal-holds/{hold.json()['id']}/release", headers=headers
    )
    assert released.status_code == 200
    with session_factory() as db:
        assert purge_expired_evidence(db, settings) == 1


def test_session_listing_logout_idle_expiry_and_concurrent_cap(platform):
    client, session_factory, settings = platform
    settings.max_sessions_per_user = 2
    settings.session_idle_minutes = 5
    bootstrap = _bootstrap(client)
    first_login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "aix-research",
            "email": "owner@example.com",
            "password": "a-long-test-password",
        },
    ).json()
    second_login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "aix-research",
            "email": "owner@example.com",
            "password": "a-long-test-password",
        },
    ).json()
    assert client.get(
        "/v1/me", headers=_headers(bootstrap["access_token"])
    ).status_code == 401
    second_headers = _headers(second_login["access_token"])
    sessions = client.get("/v1/auth/sessions", headers=second_headers)
    assert sessions.status_code == 200
    assert len(sessions.json()) == 2
    assert sum(item["current"] for item in sessions.json()) == 1

    assert client.post("/v1/auth/logout", headers=second_headers).status_code == 204
    assert client.get("/v1/me", headers=second_headers).status_code == 401

    first_headers = _headers(first_login["access_token"])
    with session_factory() as db:
        credential = db.scalar(
            select(Credential).where(
                Credential.token_hash
                == hash_token(first_login["access_token"], settings.token_pepper)
            )
        )
        credential.last_used_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        db.commit()
    expired = client.get("/v1/me", headers=first_headers)
    assert expired.status_code == 401
    assert "inactivity" in expired.json()["error"]["message"]


def test_webhook_delivery_and_privacy_export(platform, example_assessment):
    client, session_factory, settings = platform
    owner = _bootstrap(client)
    headers = _headers(owner["access_token"])
    webhook = client.post(
        "/v1/webhooks",
        headers=headers,
        json={
            "url": "https://hooks.example.test/aix",
            "events": ["assessment.finalized"],
        },
    )
    assert webhook.status_code == 201, webhook.text
    signing_secret = webhook.json()["signing_secret"]
    assert signing_secret.startswith("aixwh_")
    metadata_target = client.post(
        "/v1/webhooks",
        headers=headers,
        json={
            "url": "http://169.254.169.254/latest/meta-data",
            "events": ["assessment.finalized"],
        },
    )
    assert metadata_target.status_code == 422

    system = client.post(
        "/v1/systems",
        headers=headers,
        json={"name": "Webhook Model", "kind": "ai_system"},
    ).json()
    assessment = client.post(
        "/v1/assessments",
        headers=headers,
        json={"system_id": system["id"], "assessment": example_assessment},
    ).json()
    client.post(f"/v1/assessments/{assessment['id']}/submit", headers=headers)
    client.post(f"/v1/assessments/{assessment['id']}/approve", headers=headers)
    finalized = client.post(
        f"/v1/assessments/{assessment['id']}/finalize", headers=headers
    )
    assert finalized.status_code == 200

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["signature"] = request.headers["X-AIx-Signature"]
        captured["timestamp"] = request.headers["X-AIx-Timestamp"]
        return httpx.Response(204)

    with session_factory() as db, httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as webhook_client:
        delivery = deliver_next_webhook(db, settings, client=webhook_client)
        assert delivery is not None
        assert delivery.status == "succeeded"
        assert delivery.response_code == 204
        assert json.loads(captured["body"])["type"] == "assessment.finalized"
        import hmac

        expected = hmac.new(
            signing_secret.encode(),
            captured["timestamp"].encode() + b"." + captured["body"],
            sha256,
        ).hexdigest()
        assert captured["signature"] == f"sha256={expected}"

    export_response = client.post("/v1/privacy/exports", headers=headers)
    assert export_response.status_code == 202
    request_id = export_response.json()["id"]
    with session_factory() as db:
        processed = process_next_privacy_request(db, settings)
        assert processed is not None
        assert processed.id == request_id
        assert processed.status == "completed"
        serialized = json.dumps(processed.result_json)
        assert "password_hash" not in serialized
        assert "token_hash" not in serialized
        assert "secret_ciphertext" not in serialized
        assert "Webhook Model" in serialized

    deletion = client.post(
        "/v1/privacy/deletions",
        headers=headers,
        json={"confirmation": "delete aix-research"},
    )
    assert deletion.status_code == 202
    cancelled = client.post(
        f"/v1/privacy/requests/{deletion.json()['id']}/cancel",
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_request_controls_and_metrics(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite://",
        token_pepper="request-control-pepper",
        webhook_secret_pepper="request-webhook-pepper",
        storage_path=tmp_path / "objects",
        rate_limit_requests=2,
        request_max_bytes=1024,
    )
    app = create_app(settings=settings, create_schema=False)

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        first = client.get("/v1/me")
        second = client.get("/v1/me")
        third = client.get("/v1/me")
        assert first.status_code == 401
        assert second.status_code == 401
        assert third.status_code == 429
        assert third.json()["error"]["code"] == "rate_limited"
        assert first.headers["x-content-type-options"] == "nosniff"
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "aix_http_requests_total" in metrics.text

    engine.dispose()


def test_validation_uses_stable_error_envelope(platform):
    client, _, _ = platform
    response = client.post("/v1/bootstrap", json={"organization_name": "x"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["context"]["errors"]


def test_oidc_disabled_and_production_settings_are_validated(platform):
    client, _, _ = platform
    response = client.get(
        "/v1/auth/oidc/login",
        params={"organization_slug": "aix-research"},
        follow_redirects=False,
    )
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "OIDC is not configured"

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(
            oidc_issuer="https://identity.example.test",
            token_pepper="test-token-pepper-value",
            webhook_secret_pepper="test-webhook-secret-pepper",
        )
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            token_pepper="production-token-pepper-value",
            webhook_secret_pepper="production-webhook-secret-pepper",
            storage_backend="s3",
            s3_bucket="evidence",
        )


def test_oidc_login_provisions_user_and_hands_token_to_spa(
    monkeypatch, tmp_path
):
    class FakeOIDCClient:
        async def authorize_redirect(self, request, redirect_uri):
            assert redirect_uri == "http://api.test/v1/auth/oidc/callback"
            return RedirectResponse("https://identity.example.test/authorize")

        async def authorize_access_token(self, request):
            return {
                "userinfo": {
                    "sub": "subject-123",
                    "email": "sso-user@example.com",
                    "email_verified": True,
                    "name": "SSO User",
                    "aix_role": "assessor",
                }
            }

    class FakeOAuth:
        def register(self, **kwargs):
            self.oidc = FakeOIDCClient()

    monkeypatch.setattr("aix_platform.app.OAuth", FakeOAuth)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite://",
        token_pepper="oidc-test-token-pepper",
        webhook_secret_pepper="oidc-test-webhook-pepper",
        storage_path=tmp_path / "evidence",
        oidc_issuer="https://identity.example.test",
        oidc_client_id="aix-test",
        oidc_client_secret="oidc-client-secret",
        oidc_redirect_uri="http://api.test/v1/auth/oidc/callback",
        oidc_web_app_url="http://web.test",
        oidc_auto_provision=True,
    )
    app = create_app(settings=settings, create_schema=False)

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app, base_url="http://api.test") as client:
        _bootstrap(client)
        login_response = client.get(
            "/v1/auth/oidc/login",
            params={"organization_slug": "aix-research"},
            follow_redirects=False,
        )
        assert login_response.status_code == 307
        callback = client.get(
            "/v1/auth/oidc/callback",
            follow_redirects=False,
        )
        assert callback.status_code == 303
        token = callback.headers["location"].split("#access_token=", 1)[1]
        principal = client.get("/v1/me", headers=_headers(token))
        assert principal.status_code == 200
        assert principal.json()["email"] == "sso-user@example.com"
        assert principal.json()["role"] == "assessor"
    engine.dispose()
