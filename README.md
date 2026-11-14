# Аренда оборудования с интеллектуальным бронированием

Веб-приложение для аренды оборудования: каталог, бронирование с проверкой
пересечений, персональные рекомендации и прогноз загрузки.
Все цены и начисления — в белорусских рублях (Br, BYN).

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 (async), asyncpg, Alembic, Pydantic v2 |
| БД | PostgreSQL 17 (Docker) |
| Frontend | React 19, TypeScript, Vite, Ant Design, TanStack Query, React Router |
| Инфраструктура | Docker Compose, uv, Git |
| Изображения | WebP + миниатюры в `data/uploads`, метаданные в PostgreSQL |

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

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Приложение: http://127.0.0.1:5173 (Vite проксирует `/api` и `/media` на backend).
При отдельном размещении собранного фронтенда настройте на веб-сервере
проксирование `/media` на backend — иначе изображения не загрузятся.

### Демо-аккаунты

Регистрация требует подтверждения email. Пока SMTP не настроен, ссылка
подтверждения пишется в лог backend и передаётся фронтенду в заголовке
`X-Debug-Verification-Token` — интерфейс сразу открывает страницу `/verify`.
Для реальной отправки заполните `SMTP_*` в `.env`.

Пароль при регистрации: не короче 8 символов, обязательно буквы и цифры,
частые пароли (`qwerty123`, `password123` и подобные) отклоняются.
В форме показывается индикатор надёжности с чек-листом требований.

| Роль | Email | Пароль |
|---|---|---|
| Администратор | `admin@example.com` | `admin12345` |
| Арендодатель | `owner@example.com` | `owner12345` |
| Клиент | `user@example.com` | `user12345` |
| Клиент 2 | `client2@example.com` | `client12345` |

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
| GET | `/equipment/{id}/recommendations` | все | похожие позиции (content-based) |
| GET | `/equipment/{id}/load-forecast` | все | прогноз загрузки по дням и часам |
| GET | `/equipment/popular` | все | популярное за 30 дней |
| POST | `/equipment` | админ | создание позиции |
| PATCH | `/equipment/{id}` | админ / владелец | редактирование |
| DELETE | `/equipment/{id}` | админ / владелец | мягкое удаление (скрытие из каталога) |
| POST | `/bookings/preview` | авторизован | расчёт по обоим тарифам и доступность |
| POST | `/bookings` | авторизован | создание брони |
| GET | `/bookings/my` | авторизован | мои брони |
| GET | `/bookings/{id}` | участник / админ | карточка брони |
| POST | `/bookings/{id}/cancel` | участник / админ | отмена с расчётом штрафа и возврата |
| POST | `/bookings/{id}/pickup` | арендодатель / админ | выдача (включая раннюю) |
| POST | `/bookings/{id}/return` | арендодатель / админ | возврат и пересчёт за неиспользованные единицы |
| POST | `/bookings/{id}/no-show` | арендодатель / админ | фиксация неявки |
| POST | `/bookings/{id}/no-show/revoke` | арендодатель / админ | снятие неявки в течение часа |
| POST | `/bookings/{id}/appeal` | участник | оспаривание решения в течение 24 часов |
| POST | `/bookings/{id}/early-return` | клиент | поломка/ЧП во время аренды → спор к админу |
| GET | `/admin/disputes` | админ | очередь споров |
| GET | `/admin/disputes/{id}` | админ | карточка спора |
| POST | `/admin/disputes/{id}/resolve` | админ | решение с суммами и виновной стороной |
| GET | `/admin/users` | админ | список пользователей, поиск и фильтр по роли |
| PATCH | `/admin/users/{id}` | админ | роль, блокировка, метка нарушителя, предмодерация |
| GET | `/admin/stats` | админ | сводка по сервису |
| GET | `/owner/equipment` | арендодатель | свои позиции |
| POST | `/owner/equipment` | арендодатель | создание своей позиции |
| PATCH | `/owner/equipment/{id}` | арендодатель | редактирование своей позиции |
| DELETE | `/owner/equipment/{id}` | арендодатель | скрытие позиции (запрещено при активных бронях) |
| GET | `/owner/bookings` | арендодатель | брони по своим позициям |
| GET | `/owner/stats` | арендодатель | статистика: позиции, брони, выручка, споры |
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
