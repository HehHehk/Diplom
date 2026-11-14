# Перенос проекта на другое устройство

Цель: развернуть проект на чистой машине за 10–15 минут, без ручных правок кода.

## Что переносится через Git

Всё, что нужно для запуска: исходный код, миграции, seed-скрипт, конфигурация
Docker и lock-файлы зависимостей. База данных **не переносится** — она
пересоздаётся миграциями и наполняется seed-скриптом.

## Требования на новой машине

| Компонент | Версия | Проверка |
|---|---|---|
| Docker Desktop | 4.x+ (с WSL2 на Windows) | `docker --version` |
| uv | 0.13+ | `uv --version` |
| Node.js | 22+ | `node --version` |
| Git | 2.40+ | `git --version` |

## Пошагово

```bash
git clone <repo-url> && cd Diplom
cp .env.example .env

docker compose up -d db
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload
```

Проверка: `http://127.0.0.1:8000/health` → `{"status":"ok","database":"ok"}`.

Frontend (когда будет готов):

```bash
cd frontend
npm ci
npm run dev
```

## Что нужно помнить

1. **`.env` не в Git.** Создаётся из `.env.example`. Секреты для продакшена
   генерируются отдельно, значение `SECRET_KEY` из шаблона — только для разработки.
2. **Порты.** По умолчанию `5432` (Postgres) и `8000` (backend). Если заняты —
   изменить в `.env` (`POSTGRES_PORT`) и в команде запуска uvicorn.
3. **Docker-образы.** При первом запуске скачаются `postgres:17-alpine` и базовый
   образ Python (~200 МБ).
4. **Права в Windows.** Проект нельзя держать в папке с ограниченными правами;
   путь без кириллицы предпочтителен.
5. **Пути.** В коде нет абсолютных путей — конфигурация читается из `.env` и
   переменных окружения.
6. **Изображения.** Файлы лежат в `data/uploads/{equipment_id}/`, в БД хранятся
   только метаданные. При переносе копируйте папку `data/` вместе с дампом БД
   (или используйте архив из `scripts/`).

## Проверка переносимости

Выполняется перед сдачей:

```bash
docker compose down -v          # удалить данные БД
rm -rf backend/.venv            # удалить виртуальное окружение
# (в новой копии репозитория)
cd backend && uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run pytest
```

Если все команды проходят на чистой копии — проект переносим.

## Резервная копия данных (опционально)

Если нужны реальные данные, а не демо:

```bash
docker exec rental_db pg_dump -U rental rental > backup.sql
# восстановление
docker exec -i rental_db psql -U rental -d rental < backup.sql
```

Файлы `*.sql` и каталог `backups/` исключены из Git.
