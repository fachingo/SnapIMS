from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from itsdangerous import BadSignature, URLSafeTimedSerializer

COOKIE = "snapims_session"
SESSION_MAX_AGE_SECONDS = 86400
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
MIN_SECRET_LENGTH = 32


def generate_secret() -> str:
    """Return a session-signing secret suitable for SNAPIMS_AUTH_SECRET."""
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    payload = base64.urlsafe_b64encode(salt + digest).decode()
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${payload}"


def _parse_password_hash(encoded: str) -> tuple[int, int, int, bytes, bytes] | None:
    parts = encoded.split("$")
    try:
        if len(parts) == 5 and parts[0] == "scrypt":
            n = int(parts[1])
            r = int(parts[2])
            p = int(parts[3])
            payload = parts[4]
        elif len(parts) == 2 and parts[0] == "scrypt":
            # Backward compatibility for hashes generated before parameters were embedded.
            n, r, p = SCRYPT_N, SCRYPT_R, SCRYPT_P
            payload = parts[1]
        else:
            return None
        if n <= 0 or r <= 0 or p <= 0 or n > 2**20:
            return None
        raw = base64.urlsafe_b64decode(payload.encode())
        if len(raw) <= 16:
            return None
        return n, r, p, raw[:16], raw[16:]
    except (ValueError, TypeError, binascii.Error):
        return None


def verify_password(password: str, encoded: str) -> bool:
    try:
        parsed = _parse_password_hash(encoded)
        if not parsed:
            return False
        n, r, p, salt, expected = parsed
        actual = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def authentication_problem(secret: str, password_hash: str) -> str:
    """Return a configuration problem, or an empty string when auth is usable/disabled."""
    if not secret and not password_hash:
        return ""
    if not secret:
        return "SNAPIMS_AUTH_SECRET must be set when SNAPIMS_ADMIN_PASSWORD_HASH is set."
    if len(secret) < MIN_SECRET_LENGTH:
        return f"SNAPIMS_AUTH_SECRET must be at least {MIN_SECRET_LENGTH} characters."
    if not password_hash:
        return "SNAPIMS_ADMIN_PASSWORD_HASH must be set when SNAPIMS_AUTH_SECRET is set."
    if _parse_password_hash(password_hash) is None:
        return "SNAPIMS_ADMIN_PASSWORD_HASH is not a supported SnapIMS scrypt hash."
    return ""


def authentication_enabled(secret: str, password_hash: str) -> bool:
    return bool(secret and password_hash and not authentication_problem(secret, password_hash))


def serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret, salt="snapims-session")


def issue_session(secret: str, username: str) -> str:
    return serializer(secret).dumps({"sub": username})


def read_session(secret: str, value: str, max_age: int = SESSION_MAX_AGE_SECONDS) -> str | None:
    try:
        return serializer(secret).loads(value, max_age=max_age).get("sub")
    except (BadSignature, AttributeError):
        return None
