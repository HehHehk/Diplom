from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hash.verify(password, hashed)
    except Exception:  # noqa: BLE001 - повреждённый хеш не должен ронять запрос
        return False


def create_access_token(subject: str | int, expires_minutes: int | None = None) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(
        minutes=expires_minutes
        if expires_minutes is not None
        else settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {"sub": str(subject), "iat": now, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


__all__ = [
    "JWTError",
    "create_access_token",
    "decode_token",
    "hash_password",
    "verify_password",
]
