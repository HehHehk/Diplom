from collections import defaultdict, deque
from datetime import timedelta
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserRead, UserUpdate

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
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    email = data.email.lower()
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        )

    user = User(
        email=email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=UserRole(data.role),
        timezone=data.timezone or "Europe/Moscow",
        timezone_source="manual" if data.timezone else "fallback",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


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
