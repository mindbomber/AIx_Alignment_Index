from __future__ import annotations

from base64 import b32decode, b32encode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac, sha256
import hmac
import secrets
import struct


PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def new_token(prefix: str) -> str:
    secret = urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    return f"{prefix}_{secret}"


def hash_token(token: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), token.encode(), sha256).hexdigest()


def expires_in(*, minutes: int = 0, days: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes, days=days)


def new_totp_secret() -> str:
    return b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, *, at: datetime | None = None) -> str:
    moment = at or datetime.now(timezone.utc)
    counter = int(moment.timestamp()) // 30
    padded = secret.upper() + "=" * (-len(secret) % 8)
    digest = hmac.new(
        b32decode(padded), struct.pack(">Q", counter), "sha1"
    ).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp(secret: str, code: str, *, at: datetime | None = None) -> bool:
    moment = at or datetime.now(timezone.utc)
    normalized = code.replace(" ", "")
    return any(
        hmac.compare_digest(
            totp_code(secret, at=moment + timedelta(seconds=offset * 30)),
            normalized,
        )
        for offset in (-1, 0, 1)
    )


def new_recovery_codes(count: int = 10) -> list[str]:
    return [
        "-".join(
            (
                secrets.token_hex(2).upper(),
                secrets.token_hex(2).upper(),
                secrets.token_hex(2).upper(),
            )
        )
        for _ in range(count)
    ]
