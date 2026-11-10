# Модель данных (ER-диаграмма)

```mermaid
erDiagram
    USERS ||--o{ BOOKINGS : "оформляет"
    USERS ||--o{ INTERACTIONS : "совершает"
    EQUIPMENT ||--o{ BOOKINGS : "бронируется"
    EQUIPMENT ||--o{ INTERACTIONS : "просматривается"

    USERS {
        int id PK
        string email UK "уникальный логин"
        string hashed_password
        string full_name
        enum role "user | admin"
        bool is_active
        datetime created_at
    }

    EQUIPMENT {
        int id PK
        string title
        text description
        string category "индекс для фильтров"
        string brand
        numeric price_per_day
        int quantity "доступное количество"
        jsonb specs "характеристики для рекомендаций"
        string image_url
        bool is_active
        datetime created_at
        datetime updated_at
    }

    BOOKINGS {
        int id PK
        int user_id FK
        int equipment_id FK
        datetime start_at "начало аренды"
        datetime end_at "окончание аренды"
        int quantity
        numeric total_price
        enum status "pending | confirmed | cancelled | completed"
        datetime created_at
        datetime updated_at
    }

    INTERACTIONS {
        int id PK
        int user_id FK "nullable — анонимные просмотры"
        int equipment_id FK
        enum type "view | favorite | booking"
        datetime created_at
    }
```

## Ключевые решения

1. **`equipment.quantity`** — оборудование одной модели может быть в нескольких
   экземплярах, поэтому проверка пересечений считает не факт брони, а сумму
   количеств в пересекающемся интервале.
2. **`bookings` (start_at, end_at)** — интервалы полуоткрытые: бронь A и бронь B
   не конфликтуют, если `A.end_at <= B.start_at` или `B.end_at <= A.start_at`.
   Дополнительно учитывается буфер между бронями (`BOOKING_BUFFER_MINUTES`).
3. **`bookings` (equipment_id, start_at, end_at)** — составной индекс под запрос
   проверки пересечений, самый нагруженный запрос системы.
4. **`equipment.specs` (JSONB)** — произвольные характеристики (мощность, вес,
   давление и т.д.), из которых строится вектор для content-based рекомендаций.
   JSONB выбран вместо отдельной таблицы свойств, чтобы не усложнять схему.
5. **`interactions`** — история просмотров: источник данных для блока
   «популярное» и для холодного старта рекомендаций.
6. **Статусы** хранятся как `VARCHAR` (`native_enum=False`): проще миграции,
   не нужно создавать типы в PostgreSQL вручную.
