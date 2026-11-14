import asyncio
import hashlib
import logging
import secrets
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("app.email")


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_verification_link(token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/verify?token={token}"


def _send_smtp(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    use_ssl = settings.smtp_ssl or settings.smtp_port == 465
    if use_ssl:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)

    with server:
        if not use_ssl and settings.smtp_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)


def send_test_email(to: str) -> None:
    _send_smtp(to, "Проверка SMTP — АрендаПро", "Тестовое письмо. SMTP настроен корректно.")


async def send_verification_email(email: str, token: str) -> None:
    link = build_verification_link(token)
    text = (
        "Здравствуйте!\n\n"
        "Подтвердите адрес электронной почты, чтобы начать пользоваться сервисом:\n"
        f"{link}\n\n"
        f"Ссылка действует {settings.email_verification_ttl_hours} часов.\n"
        "Если вы не регистрировались, просто проигнорируйте письмо."
    )

    if settings.smtp_host:
        try:
            await asyncio.to_thread(_send_smtp, email, "Подтверждение email — АрендаПро", text)
        except Exception:
            logger.exception("Не удалось отправить письмо на %s", email)
    else:
        logger.warning("SMTP не настроен. Ссылка подтверждения: %s", link)


def debug_token_available() -> bool:
    return settings.email_debug_return_token and not settings.smtp_host
