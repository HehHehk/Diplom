"""Проверка SMTP-настроек.

Запуск:
    uv run python -m app.smtp_check recipient@example.com
"""

import sys

from app.core.config import settings
from app.services import email_service


def main() -> int:
    if not settings.smtp_host:
        print("SMTP не настроен: SMTP_HOST пуст.")
        return 1

    recipient = sys.argv[1] if len(sys.argv) > 1 else settings.smtp_user
    if not recipient:
        print("Укажите получателя: python -m app.smtp_check you@example.com")
        return 1

    print(f"SMTP: {settings.smtp_host}:{settings.smtp_port}")
    print(f"Пользователь: {settings.smtp_user or 'без авторизации'}")
    print(f"Получатель: {recipient}")
    try:
        email_service.send_test_email(recipient)
    except Exception as exc:  # noqa: BLE001 - диагностический скрипт
        print(f"ОШИБКА: {type(exc).__name__}: {exc}")
        return 1
    print("Письмо отправлено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
