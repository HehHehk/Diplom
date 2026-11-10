# Аренда оборудования с интеллектуальным бронированием

Веб-приложение для аренды оборудования: каталог, бронирование с проверкой
пересечений, персональные рекомендации и прогноз загрузки.

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 (async), asyncpg, Alembic, Pydantic v2 |
| БД | PostgreSQL 17 (Docker) |
| Frontend | React 19, TypeScript, Vite, Ant Design, TanStack Query *(в разработке)* |
| Инфраструктура | Docker Compose, uv, Git |

## Требования

- Windows / Linux / macOS
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (запущен)
- [uv](https://docs.astral.sh/uv/)
- Node.js 22+ и npm (для frontend)

## Быстрый старт

```bash
# 1. клонировать репозиторий
git clone <repo-url> && cd Diplom

# 2. создать .env из шаблона
cp .env.example .env

# 3. поднять PostgreSQL
docker compose up -d db

# 4. установить зависимости backend
cd backend && uv sync

# 5. применить миграции и наполнить демо-данными
uv run alembic upgrade head
uv run python -m app.seed
```

Запуск API:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- Проверка: http://127.0.0.1:8000/health

### Демо-аккаунты

| Роль | Email | Пароль |
|---|---|---|
| Администратор | `admin@example.com` | `admin12345` |
| Арендодатель | `owner@example.com` | `owner12345` |
| Клиент | `user@example.com` | `user12345` |

## API

| Метод | Путь | Доступ | Назначение |
|---|---|---|---|
| POST | `/auth/register` | все | регистрация |
| POST | `/auth/login` | все | вход (OAuth2 form, `username` = email) |
| GET | `/auth/me` | авторизован | текущий пользователь |
| GET | `/equipment` | все | каталог: поиск, фильтры, сортировка, пагинация |
| GET | `/equipment/categories` | все | список категорий для фильтров |
| GET | `/equipment/{id}` | все | карточка + запись просмотра в `interactions` |
| GET | `/equipment/{id}/availability` | все | занятые интервалы для календаря |
| POST | `/equipment` | админ | создание позиции |
| PATCH | `/equipment/{id}` | админ / владелец | редактирование |
| DELETE | `/equipment/{id}` | админ / владелец | мягкое удаление (скрытие из каталога) |
| POST | `/bookings/preview` | авторизован | расчёт по обоим тарифам и доступность |
| POST | `/bookings` | авторизован | создание брони |
| GET | `/bookings/my` | авторизован | мои брони |
| GET | `/bookings/{id}` | участник / админ | карточка брони |
| POST | `/bookings/{id}/cancel` | участник / админ | отмена с расчётом штрафа и возврата |
| GET | `/health` | все | проверка API и БД |

Параметры каталога: `q`, `category`, `brand`, `min_price`, `max_price`,
`sort` (`newest` / `price_asc` / `price_desc` / `title`), `limit`, `offset`,
`include_inactive` (только для админа).

Правила бронирования, тарифы, отмены и споры описаны в
[docs/booking-rules.md](docs/booking-rules.md).


## Структура проекта

```
.
├── backend/
│   ├── app/
│   │   ├── api/          # роутеры FastAPI
│   │   ├── core/         # конфигурация, безопасность
│   │   ├── db/           # подключение к БД, Base
│   │   ├── models/       # SQLAlchemy-модели
│   │   ├── schemas/      # Pydantic-схемы
│   │   ├── services/     # бизнес-логика (бронирование, рекомендации)
│   │   ├── main.py       # точка входа
│   │   └── seed.py       # демо-данные
│   ├── alembic/          # миграции
│   └── tests/            # pytest
├── frontend/             # React + TS (в разработке)
├── docs/                 # документация, диаграммы
├── scripts/              # вспомогательные скрипты
└── docker-compose.yml
```

## Полезные команды

```bash
# из каталога backend/

uv run alembic revision --autogenerate -m "описание"   # новая миграция
uv run alembic upgrade head                            # применить
uv run alembic downgrade -1                            # откатить одну

uv run python -m app.seed            # наполнить, если пусто
uv run python -m app.seed --reset    # очистить и наполнить заново

uv run pytest                        # тесты
uv run ruff check .                  # линтер
uv run ruff format .                 # форматирование
```

```bash
# из корня

docker compose up -d db              # только БД (обычный режим разработки)
docker compose --profile full up -d  # БД + backend в контейнере
docker compose down                  # остановить
docker compose down -v               # остановить и удалить данные БД
```

Пересоздание базы с нуля:

```bash
docker compose down -v && docker compose up -d db
cd backend && uv run alembic upgrade head && uv run python -m app.seed --reset
```

## Перенос на другое устройство

Проект полностью воспроизводим: зависимости зафиксированы в `uv.lock` и
`package-lock.json`, БД создаётся миграциями и seed-скриптом. Подробная
инструкция — в [docs/portability.md](docs/portability.md).
