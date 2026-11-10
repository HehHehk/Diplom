"""Наполнение базы демонстрационными данными.

Запуск:
    python -m app.seed           # добавить, если пусто
    python -m app.seed --reset   # очистить и создать заново
"""

import argparse
import asyncio
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pwdlib import PasswordHash
from sqlalchemy import func, select, text

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.booking import Booking
from app.models.enums import BookingStatus, InteractionType, UserRole
from app.models.equipment import Equipment
from app.models.interaction import Interaction
from app.models.user import User

password_hash = PasswordHash.recommended()

DEMO_USERS = [
    {
        "email": "admin@example.com",
        "password": "admin12345",
        "full_name": "Администратор",
        "role": UserRole.admin,
    },
    {
        "email": "user@example.com",
        "password": "user12345",
        "full_name": "Иван Петров",
        "role": UserRole.user,
    },
]

# (title, category, brand, price_per_day, quantity, specs)
EQUIPMENT: list[tuple[str, str, str, float, int, dict]] = [
    # Дрели и перфораторы
    (
        "Перфоратор Bosch GBH 2-26",
        "Дрели и перфораторы",
        "Bosch",
        650,
        4,
        {"power_w": 800, "weight_kg": 2.7, "impact_j": 2.7},
    ),
    (
        "Перфоратор Makita HR2470",
        "Дрели и перфораторы",
        "Makita",
        590,
        3,
        {"power_w": 780, "weight_kg": 2.9, "impact_j": 2.4},
    ),
    (
        "Дрель-шуруповёрт DeWalt DCD796",
        "Дрели и перфораторы",
        "DeWalt",
        450,
        5,
        {"power_w": 460, "weight_kg": 1.8, "battery_h": 4},
    ),
    (
        "Дрель ударная Metabo SBE 650",
        "Дрели и перфораторы",
        "Metabo",
        320,
        3,
        {"power_w": 650, "weight_kg": 2.2},
    ),
    (
        "Отбойный молоток Bosch GSH 16-28",
        "Дрели и перфораторы",
        "Bosch",
        1800,
        2,
        {"power_w": 1750, "weight_kg": 16.5, "impact_j": 41},
    ),
    (
        "Шуруповёрт Makita DF333D",
        "Дрели и перфораторы",
        "Makita",
        300,
        6,
        {"power_w": 280, "weight_kg": 1.3, "battery_h": 3},
    ),
    # Сварочное оборудование
    (
        "Сварочный инвертор Kemppi Minarc 150",
        "Сварочное оборудование",
        "Kemppi",
        900,
        3,
        {"current_a": 150, "weight_kg": 4.6, "voltage_v": 230},
    ),
    (
        "Сварочный аппарат Ресанта САИ 220",
        "Сварочное оборудование",
        "Ресанта",
        550,
        4,
        {"current_a": 220, "weight_kg": 9.8, "voltage_v": 230},
    ),
    (
        "Аргоновый аппарат Aurora PRO TIG 200",
        "Сварочное оборудование",
        "Aurora",
        1500,
        2,
        {"current_a": 200, "weight_kg": 18.0, "voltage_v": 220},
    ),
    (
        "Полуавтомат Fubag IRMIG 200",
        "Сварочное оборудование",
        "Fubag",
        1200,
        2,
        {"current_a": 200, "weight_kg": 26.0},
    ),
    # Садовый инструмент
    (
        "Бензопила Husqvarna 450",
        "Садовый инструмент",
        "Husqvarna",
        700,
        3,
        {"power_w": 2400, "weight_kg": 5.0, "bar_cm": 45},
    ),
    (
        "Бензопила Stihl MS 180",
        "Садовый инструмент",
        "Stihl",
        600,
        4,
        {"power_w": 2000, "weight_kg": 4.0, "bar_cm": 40},
    ),
    (
        "Триммер Husqvarna 128R",
        "Садовый инструмент",
        "Husqvarna",
        500,
        3,
        {"power_w": 900, "weight_kg": 7.0},
    ),
    (
        "Газонокосилка Makita ELM3711",
        "Садовый инструмент",
        "Makita",
        650,
        2,
        {"power_w": 1400, "weight_kg": 14.0, "width_cm": 37},
    ),
    (
        "Культиватор Daewoo DATM 500",
        "Садовый инструмент",
        "Daewoo",
        1100,
        2,
        {"power_w": 1600, "weight_kg": 26.0},
    ),
    (
        "Снегоуборщик Karcher STH 6.0",
        "Садовый инструмент",
        "Karcher",
        1400,
        1,
        {"power_w": 2800, "weight_kg": 38.0},
    ),
    # Клининг
    (
        "Пылесос строительный Karcher NT 30/1",
        "Клининг",
        "Karcher",
        700,
        3,
        {"power_w": 1380, "capacity_l": 30, "weight_kg": 8.5},
    ),
    (
        "Пылесос моющий Karcher SE 4001",
        "Клининг",
        "Karcher",
        950,
        2,
        {"power_w": 1400, "capacity_l": 14},
    ),
    (
        "Мойка высокого давления Karcher K5",
        "Клининг",
        "Karcher",
        1100,
        3,
        {"pressure_bar": 145, "power_w": 2100, "weight_kg": 12.0},
    ),
    (
        "Мойка высокого давления Stihl RE 120",
        "Клининг",
        "Stihl",
        900,
        2,
        {"pressure_bar": 110, "power_w": 1400},
    ),
    (
        "Поломойная машина Karcher BR 40/10",
        "Клининг",
        "Karcher",
        1800,
        1,
        {"power_w": 1100, "capacity_l": 10},
    ),
    # Фото и видео
    (
        "Камера Sony A7 IV",
        "Фото и видео",
        "Sony",
        2500,
        2,
        {"resolution_mp": 33, "weight_kg": 0.66, "video_4k": 1},
    ),
    (
        "Камера Canon EOS R6",
        "Фото и видео",
        "Canon",
        2300,
        2,
        {"resolution_mp": 20, "weight_kg": 0.68, "video_4k": 1},
    ),
    (
        "Объектив Sony 24-70mm f/2.8 GM",
        "Фото и видео",
        "Sony",
        1500,
        2,
        {"focal_mm": 24, "weight_kg": 0.89},
    ),
    (
        "Штатив Manfrotto MT055",
        "Фото и видео",
        "Manfrotto",
        400,
        4,
        {"weight_kg": 2.5, "max_load_kg": 9},
    ),
    ("Стабилизатор DJI RS 3", "Фото и видео", "DJI", 900, 2, {"weight_kg": 1.3, "max_load_kg": 3}),
    (
        "Квадрокоптер DJI Air 3",
        "Фото и видео",
        "DJI",
        1800,
        2,
        {"resolution_mp": 48, "weight_kg": 0.72, "battery_min": 46},
    ),
    # Звук и свет
    (
        "Акустическая система JBL EON715",
        "Звук и свет",
        "JBL",
        1200,
        3,
        {"power_w": 1300, "weight_kg": 17.0},
    ),
    (
        "Микшерный пульт Yamaha MG12XU",
        "Звук и свет",
        "Yamaha",
        800,
        2,
        {"channels": 12, "weight_kg": 3.3},
    ),
    ("Микрофон Shure SM58", "Звук и свет", "Shure", 250, 6, {"weight_kg": 0.3, "type": "dynamic"}),
    (
        "Световая голова Robe LEDBeam 150",
        "Звук и свет",
        "Robe",
        1500,
        4,
        {"power_w": 180, "weight_kg": 6.4},
    ),
    (
        "Дым-машина Antari Z-1500",
        "Звук и свет",
        "Antari",
        700,
        2,
        {"power_w": 1500, "capacity_l": 2.5},
    ),
    # Туризм и кемпинг
    (
        "Палатка 4-местная Naturehike",
        "Туризм и кемпинг",
        "Naturehike",
        450,
        4,
        {"capacity_person": 4, "weight_kg": 4.2},
    ),
    (
        "Спальный мешок Deuter",
        "Туризм и кемпинг",
        "Deuter",
        250,
        6,
        {"comfort_c": -5, "weight_kg": 1.6},
    ),
    (
        "Газовый гриль Weber Q1200",
        "Туризм и кемпинг",
        "Weber",
        900,
        2,
        {"power_w": 2200, "weight_kg": 12.0},
    ),
    ("Термобокс Igloo 45 л", "Туризм и кемпинг", "Igloo", 300, 3, {"capacity_l": 45}),
    (
        "Каяк Intex Explorer K2",
        "Туризм и кемпинг",
        "Intex",
        700,
        2,
        {"capacity_person": 2, "weight_kg": 14.0},
    ),
    # Климат
    (
        "Тепловая пушка Ballu BHP-P2-3",
        "Климат",
        "Ballu",
        600,
        4,
        {"power_w": 3000, "weight_kg": 4.5},
    ),
    (
        "Кондиционер мобильный Ballu BPAC-09",
        "Климат",
        "Ballu",
        900,
        3,
        {"power_w": 900, "btu": 9000},
    ),
    (
        "Осушитель воздуха Dantherm CDT 30",
        "Климат",
        "Dantherm",
        1000,
        2,
        {"capacity_l_day": 30, "power_w": 650},
    ),
    ("Увлажнитель Boneco S450", "Климат", "Boneco", 500, 2, {"capacity_l": 7, "power_w": 60}),
    # Генераторы и питание
    (
        "Генератор Honda EU22i",
        "Генераторы и питание",
        "Honda",
        1800,
        2,
        {"power_w": 2200, "weight_kg": 21.0, "voltage_v": 230},
    ),
    (
        "Генератор Hyundai HHY 3050FE",
        "Генераторы и питание",
        "Hyundai",
        1300,
        2,
        {"power_w": 3000, "weight_kg": 45.0},
    ),
    (
        "Портативная станция EcoFlow River 2 Pro",
        "Генераторы и питание",
        "EcoFlow",
        1200,
        3,
        {"capacity_wh": 768, "power_w": 800},
    ),
    # Леса и вышки
    (
        "Строительные леса, 2 секции",
        "Строительные леса",
        "Стройтех",
        800,
        2,
        {"height_m": 4.0, "load_kg": 200},
    ),
    ("Вышка-тура 6 м", "Строительные леса", "Стройтех", 1500, 1, {"height_m": 6.0, "load_kg": 150}),
    ("Подмости 3 м", "Строительные леса", "Стройтех", 500, 2, {"height_m": 3.0, "load_kg": 150}),
]


async def reset_tables() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE interactions, bookings, equipment, users RESTART IDENTITY CASCADE")
        )


async def seed(reset: bool = False) -> None:
    rnd = random.Random(settings.seed_random)
    now = datetime.now(UTC)

    if reset:
        await reset_tables()
        print("Таблицы очищены.")

    async with SessionLocal() as session:
        existing = await session.scalar(select(func.count()).select_from(Equipment))
        if existing:
            print(f"В базе уже {existing} единиц оборудования — пропускаю (используйте --reset).")
            return

        users: list[User] = []
        for item in DEMO_USERS:
            user = await session.scalar(select(User).where(User.email == item["email"]))
            if user is None:
                user = User(
                    email=item["email"],
                    hashed_password=password_hash.hash(item["password"]),
                    full_name=item["full_name"],
                    role=item["role"],
                )
                session.add(user)
            users.append(user)

        equipment: list[Equipment] = []
        for title, category, brand, price, quantity, specs in EQUIPMENT:
            item = Equipment(
                title=title,
                category=category,
                brand=brand,
                price_per_day=Decimal(str(price)),
                quantity=quantity,
                specs=specs,
                description=f"{category}. {brand}. Доступно единиц: {quantity}.",
                image_url="",
            )
            session.add(item)
            equipment.append(item)

        await session.flush()
        client = next(u for u in users if u.role == UserRole.user)

        bookings: list[Booking] = []
        for _ in range(140):
            item = rnd.choice(equipment)
            days_ago = rnd.randint(1, 90)
            start = (now - timedelta(days=days_ago)).replace(
                hour=rnd.randint(8, 16), minute=0, second=0, microsecond=0
            )
            duration_days = rnd.randint(1, 5)
            end = start + timedelta(days=duration_days)
            qty = rnd.randint(1, min(2, item.quantity))
            bookings.append(
                Booking(
                    user_id=client.id,
                    equipment_id=item.id,
                    start_at=start,
                    end_at=end,
                    quantity=qty,
                    total_price=item.price_per_day * qty * duration_days,
                    status=BookingStatus.cancelled
                    if rnd.random() < 0.12
                    else BookingStatus.completed,
                )
            )

        for _ in range(30):
            item = rnd.choice(equipment)
            start = (now + timedelta(days=rnd.randint(0, 20))).replace(
                hour=rnd.randint(8, 16), minute=0, second=0, microsecond=0
            )
            duration_days = rnd.randint(1, 4)
            end = start + timedelta(days=duration_days)
            qty = rnd.randint(1, min(2, item.quantity))
            bookings.append(
                Booking(
                    user_id=client.id,
                    equipment_id=item.id,
                    start_at=start,
                    end_at=end,
                    quantity=qty,
                    total_price=item.price_per_day * qty * duration_days,
                    status=rnd.choice([BookingStatus.pending, BookingStatus.confirmed]),
                )
            )

        session.add_all(bookings)
        await session.flush()

        interactions: list[Interaction] = []
        for booking in bookings:
            for _ in range(rnd.randint(1, 3)):
                viewed_at = booking.start_at - timedelta(days=rnd.randint(1, 7))
                interactions.append(
                    Interaction(
                        user_id=client.id,
                        equipment_id=booking.equipment_id,
                        type=InteractionType.view,
                        created_at=viewed_at,
                    )
                )
        for _ in range(180):
            item = rnd.choice(equipment)
            interactions.append(
                Interaction(
                    user_id=client.id if rnd.random() < 0.7 else None,
                    equipment_id=item.id,
                    type=InteractionType.view,
                    created_at=now - timedelta(days=rnd.randint(0, 60)),
                )
            )

        session.add_all(interactions)
        await session.commit()

        print(
            f"Готово: {len(users)} пользователей, {len(equipment)} единиц оборудования, "
            f"{len(bookings)} броней, {len(interactions)} взаимодействий."
        )
        print("Админ: admin@example.com / admin12345")
        print("Клиент: user@example.com / user12345")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data")
    parser.add_argument("--reset", action="store_true", help="очистить таблицы перед наполнением")
    args = parser.parse_args()
    asyncio.run(seed(reset=args.reset))


if __name__ == "__main__":
    main()
