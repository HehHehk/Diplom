from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.enums import UserRole

RegistrationRole = Literal["user", "owner"]

COMMON_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "qwerty",
    "qwerty123",
    "12345678",
    "123456789",
    "admin123",
    "admin12345",
    "letmein",
    "welcome",
    "welcome1",
    "iloveyou",
    "abc12345",
    "1q2w3e4r",
}


def _validate_timezone(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Неизвестный часовой пояс") from exc
    return value


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(default="", max_length=255)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    role: RegistrationRole = "user"
    timezone: str | None = None

    _tz = field_validator("timezone")(_validate_timezone)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(character.isalpha() for character in value):
            raise ValueError("Пароль должен содержать хотя бы одну букву")
        if not any(character.isdigit() for character in value):
            raise ValueError("Пароль должен содержать хотя бы одну цифру")
        if value.lower() in COMMON_PASSWORDS:
            raise ValueError("Пароль слишком распространён — выберите другой")
        return value


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    timezone: str | None = None

    _tz = field_validator("timezone")(_validate_timezone)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "UserUpdate":
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} не может быть null")
        return self


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: UserRole
    is_active: bool
    email_verified_at: datetime | None
    timezone: str
    timezone_source: str
    created_at: datetime


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=256)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
