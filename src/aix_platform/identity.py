from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
import hmac
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .orm import UserMfa
from .security import hash_token, verify_totp


def _key(settings: Settings) -> bytes:
    return sha256(("aix-mfa:" + settings.token_pepper).encode()).digest()


def seal_mfa_secret(secret: str, settings: Settings) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key(settings)).encrypt(
        nonce, secret.encode(), b"aix-user-mfa"
    )
    return urlsafe_b64encode(nonce + ciphertext).decode()


def unseal_mfa_secret(ciphertext: str, settings: Settings) -> str:
    payload = urlsafe_b64decode(ciphertext.encode())
    return AESGCM(_key(settings)).decrypt(
        payload[:12], payload[12:], b"aix-user-mfa"
    ).decode()


def verify_mfa_code(
    db: Session,
    *,
    user_id: str,
    code: str,
    settings: Settings,
    consume_recovery: bool = True,
) -> bool:
    record = db.scalar(select(UserMfa).where(UserMfa.user_id == user_id))
    if record is None or record.enabled_at is None:
        return False
    secret = unseal_mfa_secret(record.secret_ciphertext, settings)
    if verify_totp(secret, code):
        return True
    code_hash = hash_token(code.upper(), settings.token_pepper)
    match = next(
        (
            stored
            for stored in record.recovery_code_hashes
            if hmac.compare_digest(stored, code_hash)
        ),
        None,
    )
    if match is None:
        return False
    if consume_recovery:
        record.recovery_code_hashes = [
            stored for stored in record.recovery_code_hashes if stored != match
        ]
    return True
