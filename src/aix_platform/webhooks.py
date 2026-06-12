from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import ipaddress
import secrets
import socket
from urllib.parse import urlparse
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .canonical import canonical_json
from .config import Settings
from .orm import WebhookDelivery, WebhookEndpoint


def _encryption_key(settings: Settings) -> bytes:
    return sha256(
        settings.webhook_secret_pepper.get_secret_value().encode()
    ).digest()


def seal_secret(secret: str, settings: Settings) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_encryption_key(settings)).encrypt(
        nonce, secret.encode(), b"aix-webhook-secret"
    )
    return urlsafe_b64encode(nonce + ciphertext).decode()


def unseal_secret(ciphertext: str, settings: Settings) -> str:
    payload = urlsafe_b64decode(ciphertext.encode())
    return AESGCM(_encryption_key(settings)).decrypt(
        payload[:12], payload[12:], b"aix-webhook-secret"
    ).decode()


def validate_webhook_url(url: str, settings: Settings) -> None:
    parsed = urlparse(url)
    allowed_schemes = {"https"} if settings.environment == "production" else {
        "http",
        "https",
    }
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        raise ValueError("Webhook URL must use an allowed HTTP scheme and hostname")
    if parsed.username or parsed.password:
        raise ValueError("Webhook URL must not include embedded credentials")
    try:
        literal_address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        literal_address = None
    if literal_address and (
        literal_address.is_link_local
        or literal_address.is_multicast
        or literal_address.is_reserved
        or literal_address.is_unspecified
    ):
        raise ValueError("Webhook URL targets a prohibited network")
    if settings.environment != "production":
        return
    for result in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
        address = ipaddress.ip_address(result[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
        ):
            raise ValueError("Webhook URL resolves to a prohibited network")


def enqueue_webhook_event(
    db: Session,
    *,
    organization_id: str,
    event_type: str,
    data: dict,
) -> list[WebhookDelivery]:
    event_id = str(uuid4())
    envelope = {
        "id": event_id,
        "type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    endpoints = db.scalars(
        select(WebhookEndpoint).where(
            WebhookEndpoint.organization_id == organization_id,
            WebhookEndpoint.active.is_(True),
        )
    )
    deliveries = []
    for endpoint in endpoints:
        if "*" not in endpoint.events_json and event_type not in endpoint.events_json:
            continue
        delivery = WebhookDelivery(
            organization_id=organization_id,
            endpoint_id=endpoint.id,
            event_id=event_id,
            event_type=event_type,
            payload_json=envelope,
        )
        db.add(delivery)
        deliveries.append(delivery)
    return deliveries


def deliver_next_webhook(
    db: Session,
    settings: Settings,
    *,
    client: httpx.Client | None = None,
) -> WebhookDelivery | None:
    now = datetime.now(timezone.utc)
    delivery = db.scalar(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_attempt_at <= now,
        )
        .order_by(WebhookDelivery.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if delivery is None:
        return None
    endpoint = db.get(WebhookEndpoint, delivery.endpoint_id)
    if endpoint is None or not endpoint.active:
        delivery.status = "failed"
        delivery.error = "Webhook endpoint is unavailable"
        db.commit()
        return delivery

    delivery.status = "running"
    delivery.attempts += 1
    db.commit()
    body = canonical_json(delivery.payload_json).encode()
    secret = unseal_secret(endpoint.secret_ciphertext, settings)
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, sha256
    ).hexdigest()
    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=settings.webhook_timeout_seconds,
        follow_redirects=False,
    )
    try:
        validate_webhook_url(endpoint.url, settings)
        response = active_client.post(
            endpoint.url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AIx-Webhook/0.1",
                "X-AIx-Event-ID": delivery.event_id,
                "X-AIx-Event-Type": delivery.event_type,
                "X-AIx-Timestamp": timestamp,
                "X-AIx-Signature": f"sha256={signature}",
            },
        )
        delivery.response_code = response.status_code
        if 200 <= response.status_code < 300:
            delivery.status = "succeeded"
            delivery.delivered_at = datetime.now(timezone.utc)
            delivery.error = None
        else:
            raise RuntimeError(f"Webhook returned HTTP {response.status_code}")
    except Exception as exc:
        delivery.error = str(exc)[:2000]
        if delivery.attempts >= delivery.max_attempts:
            delivery.status = "failed"
        else:
            delivery.status = "pending"
            delay = min(3600, 2 ** delivery.attempts * 15)
            delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                seconds=delay
            )
    finally:
        if owns_client:
            active_client.close()
    db.commit()
    return delivery
