from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 240_000


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(raw: str) -> bytes:
    padded = raw + "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def hash_password(password: str) -> str:
    cleaned = str(password or "")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        cleaned.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_SCHEME,
            str(PASSWORD_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    parts = str(stored_hash or "").split("$")
    if len(parts) != 4 or parts[0] != PASSWORD_SCHEME:
        return False
    try:
        iterations = int(parts[1])
        salt = _b64decode(parts[2])
        expected = _b64decode(parts[3])
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_token_digest(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def session_expires_at(*, days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")
