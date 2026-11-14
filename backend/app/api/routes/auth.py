from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import (
    ResendVerificationRequest,
    Token,
    UserCreate,
    UserRead,
    UserUpdate,
    VerifyEmailRequest,
)
from app.services import email_service

router = APIRouter(prefix="/auth", tags=["auth"])


APPROX_ATTEMPT_LIMIT = 10000
_login_failures: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.strip().lower()}"


def _check_login_rate(key: str) -> None:
    window = timedelta(minutes=settings.login_rate_limit_window_minutes).total_seconds()
    attempts = _login_failures[key]
    now = monotonic()
    while attempts and now - attempts[0] > window:
        attempts.popleft()
    if len(attempts) >= settings.login_rate_limit_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа, попробуйте позже",
        )
    if len(_login_failures) > APPROX_ATTEMPT_LIMIT:
        for stale in [k for k, q in _login_failures.items() if not q]:
            _login_failures.pop(stale, None)


def _register_failure(key: str) -> None:
    _login_failures[key].append(monotonic())


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    email = data.email.lower()
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        )

    token = email_service.generate_token()
    user = User(
        email=email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=UserRole(data.role),
        timezone=data.timezone or "Europe/Moscow",
        timezone_source="manual" if data.timezone else "fallback",
        verification_hash=email_service.hash_token(token),
        verification_expires_at=datetime.now(UTC)
        + timedelta(hours=settings.email_verification_ttl_hours),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await email_service.send_verification_email(user.email, token)
    if email_service.debug_token_available():
        response.headers["X-Debug-Verification-Token"] = token

    return user


@router.post("/verify-email", response_model=UserRead)
async def verify_email(
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    token_hash = email_service.hash_token(data.token)
    user = await db.scalar(select(User).where(User.verification_hash == token_hash))
    if user is None:
        raise HTTPException(status_code=400, detail="Ссылка недействительна")
    if user.verification_expires_at is None or user.verification_expires_at < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Срок действия ссылки истёк")

    user.email_verified_at = datetime.now(UTC)
    user.verification_hash = None
    user.verification_expires_at = None
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    data: ResendVerificationRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    if user is not None and user.email_verified_at is None:
        token = email_service.generate_token()
        user.verification_hash = email_service.hash_token(token)
        user.verification_expires_at = datetime.now(UTC) + timedelta(
            hours=settings.email_verification_ttl_hours
        )
        await db.commit()
        await email_service.send_verification_email(user.email, token)
        if email_service.debug_token_available():
            response.headers["X-Debug-Verification-Token"] = token

    return {"status": "accepted"}


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Вход по email и паролю.

    В поле `username` передаётся email (стандарт OAuth2 password flow).
    """
    key = _client_key(request, form.username)
    _check_login_rate(key)

    user = await db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not verify_password(form.password, user.hashed_password):
        _register_failure(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учётная запись заблокирована",
        )
    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Подтвердите email: проверьте письмо или запросите повторную отправку",
        )
    _login_failures.pop(key, None)
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserRead)
async def update_me(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    changes = data.model_dump(exclude_unset=True)
    if changes.get("timezone"):
        user.timezone_source = "manual"
    for field, value in changes.items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user
