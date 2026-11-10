"""РќР°РїРѕР»РЅРµРЅРёРµ Р±Р°Р·С‹ РґРµРјРѕРЅСЃС‚СЂР°С†РёРѕРЅРЅС‹РјРё РґР°РЅРЅС‹РјРё.

Р—Р°РїСѓСЃРє:
    python -m app.seed           # РґРѕР±Р°РІРёС‚СЊ, РµСЃР»Рё РїСѓСЃС‚Рѕ
    python -m app.seed --reset   # РѕС‡РёСЃС‚РёС‚СЊ Рё СЃРѕР·РґР°С‚СЊ Р·Р°РЅРѕРІРѕ
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
from app.models.enums import BillingUnit, BookingStatus, InteractionType, UserRole
from app.models.equipment import Equipment
from app.models.interaction import Interaction
from app.models.user import User

password_hash = PasswordHash.recommended()

DEMO_USERS = [
    {
        "email": "admin@example.com",
        "password": "admin12345",
        "full_name": "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ",
        "role": UserRole.admin,
    },
    {
        "email": "user@example.com",
        "password": "user12345",
        "full_name": "РРІР°РЅ РџРµС‚СЂРѕРІ",
        "role": UserRole.user,
    },
    {
        "email": "owner@example.com",
        "password": "owner12345",
        "full_name": "РћРћРћ В«РџСЂРѕРєР°С‚-РЎРµСЂРІРёСЃВ»",
        "role": UserRole.owner,
    },
]

WORKING_HOURS = {
    "mon": [["09:00", "20:00"]],
    "tue": [["09:00", "20:00"]],
    "wed": [["09:00", "20:00"]],
    "thu": [["09:00", "20:00"]],
    "fri": [["09:00", "20:00"]],
    "sat": [["10:00", "18:00"]],
    "sun": [],
}

# (title, category, brand, price_per_day, quantity, specs)
EQUIPMENT: list[tuple[str, str, str, float, int, dict]] = [
    # Р”СЂРµР»Рё Рё РїРµСЂС„РѕСЂР°С‚РѕСЂС‹
    (
        "РџРµСЂС„РѕСЂР°С‚РѕСЂ Bosch GBH 2-26",
        "Р”СЂРµР»Рё Рё РїРµСЂС„РѕСЂР°С‚РѕСЂС‹",
        "Bosch",
        650,
        4,
        {"power_w": 800, "weight_kg": 2.7, "impact_j": 2.7},
    ),
    (
        "РџРµСЂС„РѕСЂР°С‚РѕСЂ Makita HR2470",
        "Р”СЂРµР»Рё Рё РїРµСЂС„РѕСЂР°С‚РѕСЂС‹",
        "Makita",
        590,
        3,
        {"power_w": 780, "weight_kg": 2.9, "impact_j": 2.4},
    ),
    (
        "Р”СЂРµР»СЊ-С€СѓСЂСѓРїРѕРІС‘СЂС‚ DeWalt DCD796",
        "Р”СЂРµР»Рё Рё РїРµСЂС„РѕСЂР°С‚РѕСЂС‹",
        "DeWalt",
        450,
        5,
        {"power_w": 460, "weight_kg": 1.8, "battery_h": 4},
    ),
    (
        "Р”СЂРµР»СЊ СѓРґР°СЂРЅР°СЏ Metabo SBE 650",
        "Р”СЂРµР»Рё Рё РїРµСЂС„РѕСЂР°С‚РѕСЂС‹",
        "Metabo",
        320,
        3,
        {"power_w": 650, "weight_kg": 2.2},
    ),
    (
        "РћС‚Р±РѕР№РЅС‹Р№ РјРѕР»РѕС‚РѕРє Bosch GSH 16-28",
        "Р”СЂРµР»Рё Рё РїРµСЂС„РѕСЂР°С‚РѕСЂС‹",
        "Bosch",
        1800,
        2,
        {"power_w": 1750, "weight_kg": 16.5, "impact_j": 41},
    ),
    (
        "РЁСѓСЂСѓРїРѕРІС‘СЂС‚ Makita DF333D",
        "Р”СЂРµР»Рё Рё РїРµСЂС„РѕСЂР°С‚РѕСЂС‹",
        "Makita",
        300,
        6,
        {"power_w": 280, "weight_kg": 1.3, "battery_h": 3},
    ),
    # РЎРІР°СЂРѕС‡РЅРѕРµ РѕР±РѕСЂСѓРґРѕРІР°РЅРёРµ
    (
        "РЎРІР°СЂРѕС‡РЅС‹Р№ РёРЅРІРµСЂС‚РѕСЂ Kemppi Minarc 150",
        "РЎРІР°СЂРѕС‡РЅРѕРµ РѕР±РѕСЂСѓРґРѕРІР°РЅРёРµ",
        "Kemppi",
        900,
        3,
        {"current_a": 150, "weight_kg": 4.6, "voltage_v": 230},
    ),
    (
        "РЎРІР°СЂРѕС‡РЅС‹Р№ Р°РїРїР°СЂР°С‚ Р РµСЃР°РЅС‚Р° РЎРђР 220",
        "РЎРІР°СЂРѕС‡РЅРѕРµ РѕР±РѕСЂСѓРґРѕРІР°РЅРёРµ",
        "Р РµСЃР°РЅС‚Р°",
        550,
        4,
        {"current_a": 220, "weight_kg": 9.8, "voltage_v": 230},
    ),
    (
        "РђСЂРіРѕРЅРѕРІС‹Р№ Р°РїРїР°СЂР°С‚ Aurora PRO TIG 200",
        "РЎРІР°СЂРѕС‡РЅРѕРµ РѕР±РѕСЂСѓРґРѕРІР°РЅРёРµ",
        "Aurora",
        1500,
        2,
        {"current_a": 200, "weight_kg": 18.0, "voltage_v": 220},
    ),
    (
        "РџРѕР»СѓР°РІС‚РѕРјР°С‚ Fubag IRMIG 200",
        "РЎРІР°СЂРѕС‡РЅРѕРµ РѕР±РѕСЂСѓРґРѕРІР°РЅРёРµ",
        "Fubag",
        1200,
        2,
        {"current_a": 200, "weight_kg": 26.0},
    ),
    # РЎР°РґРѕРІС‹Р№ РёРЅСЃС‚СЂСѓРјРµРЅС‚
    (
        "Р‘РµРЅР·РѕРїРёР»Р° Husqvarna 450",
        "РЎР°РґРѕРІС‹Р№ РёРЅСЃС‚СЂСѓРјРµРЅС‚",
        "Husqvarna",
        700,
        3,
        {"power_w": 2400, "weight_kg": 5.0, "bar_cm": 45},
    ),
    (
        "Р‘РµРЅР·РѕРїРёР»Р° Stihl MS 180",
        "РЎР°РґРѕРІС‹Р№ РёРЅСЃС‚СЂСѓРјРµРЅС‚",
        "Stihl",
        600,
        4,
        {"power_w": 2000, "weight_kg": 4.0, "bar_cm": 40},
    ),
    (
        "РўСЂРёРјРјРµСЂ Husqvarna 128R",
        "РЎР°РґРѕРІС‹Р№ РёРЅСЃС‚СЂСѓРјРµРЅС‚",
        "Husqvarna",
        500,
        3,
        {"power_w": 900, "weight_kg": 7.0},
    ),
    (
        "Р“Р°Р·РѕРЅРѕРєРѕСЃРёР»РєР° Makita ELM3711",
        "РЎР°РґРѕРІС‹Р№ РёРЅСЃС‚СЂСѓРјРµРЅС‚",
        "Makita",
        650,
        2,
        {"power_w": 1400, "weight_kg": 14.0, "width_cm": 37},
    ),
    (
        "РљСѓР»СЊС‚РёРІР°С‚РѕСЂ Daewoo DATM 500",
        "РЎР°РґРѕРІС‹Р№ РёРЅСЃС‚СЂСѓРјРµРЅС‚",
        "Daewoo",
        1100,
        2,
        {"power_w": 1600, "weight_kg": 26.0},
    ),
    (
        "РЎРЅРµРіРѕСѓР±РѕСЂС‰РёРє Karcher STH 6.0",
        "РЎР°РґРѕРІС‹Р№ РёРЅСЃС‚СЂСѓРјРµРЅС‚",
        "Karcher",
        1400,
        1,
        {"power_w": 2800, "weight_kg": 38.0},
    ),
    # РљР»РёРЅРёРЅРі
    (
        "РџС‹Р»РµСЃРѕСЃ СЃС‚СЂРѕРёС‚РµР»СЊРЅС‹Р№ Karcher NT 30/1",
        "РљР»РёРЅРёРЅРі",
        "Karcher",
        700,
        3,
        {"power_w": 1380, "capacity_l": 30, "weight_kg": 8.5},
    ),
    (
        "РџС‹Р»РµСЃРѕСЃ РјРѕСЋС‰РёР№ Karcher SE 4001",
        "РљР»РёРЅРёРЅРі",
        "Karcher",
        950,
        2,
        {"power_w": 1400, "capacity_l": 14},
    ),
    (
        "РњРѕР№РєР° РІС‹СЃРѕРєРѕРіРѕ РґР°РІР»РµРЅРёСЏ Karcher K5",
        "РљР»РёРЅРёРЅРі",
        "Karcher",
        1100,
        3,
        {"pressure_bar": 145, "power_w": 2100, "weight_kg": 12.0},
    ),
    (
        "РњРѕР№РєР° РІС‹СЃРѕРєРѕРіРѕ РґР°РІР»РµРЅРёСЏ Stihl RE 120",
        "РљР»РёРЅРёРЅРі",
        "Stihl",
        900,
        2,
        {"pressure_bar": 110, "power_w": 1400},
    ),
    (
        "РџРѕР»РѕРјРѕР№РЅР°СЏ РјР°С€РёРЅР° Karcher BR 40/10",
        "РљР»РёРЅРёРЅРі",
        "Karcher",
        1800,
        1,
        {"power_w": 1100, "capacity_l": 10},
    ),
    # Р¤РѕС‚Рѕ Рё РІРёРґРµРѕ
    (
        "РљР°РјРµСЂР° Sony A7 IV",
        "Р¤РѕС‚Рѕ Рё РІРёРґРµРѕ",
        "Sony",
        2500,
        2,
        {"resolution_mp": 33, "weight_kg": 0.66, "video_4k": 1},
    ),
    (
        "РљР°РјРµСЂР° Canon EOS R6",
        "Р¤РѕС‚Рѕ Рё РІРёРґРµРѕ",
        "Canon",
        2300,
        2,
        {"resolution_mp": 20, "weight_kg": 0.68, "video_4k": 1},
    ),
    (
        "РћР±СЉРµРєС‚РёРІ Sony 24-70mm f/2.8 GM",
        "Р¤РѕС‚Рѕ Рё РІРёРґРµРѕ",
        "Sony",
        1500,
        2,
        {"focal_mm": 24, "weight_kg": 0.89},
    ),
    (
        "РЁС‚Р°С‚РёРІ Manfrotto MT055",
        "Р¤РѕС‚Рѕ Рё РІРёРґРµРѕ",
        "Manfrotto",
        400,
        4,
        {"weight_kg": 2.5, "max_load_kg": 9},
    ),
    (
        "РЎС‚Р°Р±РёР»РёР·Р°С‚РѕСЂ DJI RS 3",
        "Р¤РѕС‚Рѕ Рё РІРёРґРµРѕ",
        "DJI",
        900,
        2,
        {"weight_kg": 1.3, "max_load_kg": 3},
    ),
    (
        "РљРІР°РґСЂРѕРєРѕРїС‚РµСЂ DJI Air 3",
        "Р¤РѕС‚Рѕ Рё РІРёРґРµРѕ",
        "DJI",
        1800,
        2,
        {"resolution_mp": 48, "weight_kg": 0.72, "battery_min": 46},
    ),
    # Р—РІСѓРє Рё СЃРІРµС‚
    (
        "РђРєСѓСЃС‚РёС‡РµСЃРєР°СЏ СЃРёСЃС‚РµРјР° JBL EON715",
        "Р—РІСѓРє Рё СЃРІРµС‚",
        "JBL",
        1200,
        3,
        {"power_w": 1300, "weight_kg": 17.0},
    ),
    (
        "РњРёРєС€РµСЂРЅС‹Р№ РїСѓР»СЊС‚ Yamaha MG12XU",
        "Р—РІСѓРє Рё СЃРІРµС‚",
        "Yamaha",
        800,
        2,
        {"channels": 12, "weight_kg": 3.3},
    ),
    (
        "РњРёРєСЂРѕС„РѕРЅ Shure SM58",
        "Р—РІСѓРє Рё СЃРІРµС‚",
        "Shure",
        250,
        6,
        {"weight_kg": 0.3, "type": "dynamic"},
    ),
    (
        "РЎРІРµС‚РѕРІР°СЏ РіРѕР»РѕРІР° Robe LEDBeam 150",
        "Р—РІСѓРє Рё СЃРІРµС‚",
        "Robe",
        1500,
        4,
        {"power_w": 180, "weight_kg": 6.4},
    ),
    (
        "Р”С‹Рј-РјР°С€РёРЅР° Antari Z-1500",
        "Р—РІСѓРє Рё СЃРІРµС‚",
        "Antari",
        700,
        2,
        {"power_w": 1500, "capacity_l": 2.5},
    ),
    # РўСѓСЂРёР·Рј Рё РєРµРјРїРёРЅРі
    (
        "РџР°Р»Р°С‚РєР° 4-РјРµСЃС‚РЅР°СЏ Naturehike",
        "РўСѓСЂРёР·Рј Рё РєРµРјРїРёРЅРі",
        "Naturehike",
        450,
        4,
        {"capacity_person": 4, "weight_kg": 4.2},
    ),
    (
        "РЎРїР°Р»СЊРЅС‹Р№ РјРµС€РѕРє Deuter",
        "РўСѓСЂРёР·Рј Рё РєРµРјРїРёРЅРі",
        "Deuter",
        250,
        6,
        {"comfort_c": -5, "weight_kg": 1.6},
    ),
    (
        "Р“Р°Р·РѕРІС‹Р№ РіСЂРёР»СЊ Weber Q1200",
        "РўСѓСЂРёР·Рј Рё РєРµРјРїРёРЅРі",
        "Weber",
        900,
        2,
        {"power_w": 2200, "weight_kg": 12.0},
    ),
    (
        "РўРµСЂРјРѕР±РѕРєСЃ Igloo 45 Р»",
        "РўСѓСЂРёР·Рј Рё РєРµРјРїРёРЅРі",
        "Igloo",
        300,
        3,
        {"capacity_l": 45},
    ),
    (
        "РљР°СЏРє Intex Explorer K2",
        "РўСѓСЂРёР·Рј Рё РєРµРјРїРёРЅРі",
        "Intex",
        700,
        2,
        {"capacity_person": 2, "weight_kg": 14.0},
    ),
    # РљР»РёРјР°С‚
    (
        "РўРµРїР»РѕРІР°СЏ РїСѓС€РєР° Ballu BHP-P2-3",
        "РљР»РёРјР°С‚",
        "Ballu",
        600,
        4,
        {"power_w": 3000, "weight_kg": 4.5},
    ),
    (
        "РљРѕРЅРґРёС†РёРѕРЅРµСЂ РјРѕР±РёР»СЊРЅС‹Р№ Ballu BPAC-09",
        "РљР»РёРјР°С‚",
        "Ballu",
        900,
        3,
        {"power_w": 900, "btu": 9000},
    ),
    (
        "РћСЃСѓС€РёС‚РµР»СЊ РІРѕР·РґСѓС…Р° Dantherm CDT 30",
        "РљР»РёРјР°С‚",
        "Dantherm",
        1000,
        2,
        {"capacity_l_day": 30, "power_w": 650},
    ),
    (
        "РЈРІР»Р°Р¶РЅРёС‚РµР»СЊ Boneco S450",
        "РљР»РёРјР°С‚",
        "Boneco",
        500,
        2,
        {"capacity_l": 7, "power_w": 60},
    ),
    # Р“РµРЅРµСЂР°С‚РѕСЂС‹ Рё РїРёС‚Р°РЅРёРµ
    (
        "Р“РµРЅРµСЂР°С‚РѕСЂ Honda EU22i",
        "Р“РµРЅРµСЂР°С‚РѕСЂС‹ Рё РїРёС‚Р°РЅРёРµ",
        "Honda",
        1800,
        2,
        {"power_w": 2200, "weight_kg": 21.0, "voltage_v": 230},
    ),
    (
        "Р“РµРЅРµСЂР°С‚РѕСЂ Hyundai HHY 3050FE",
        "Р“РµРЅРµСЂР°С‚РѕСЂС‹ Рё РїРёС‚Р°РЅРёРµ",
        "Hyundai",
        1300,
        2,
        {"power_w": 3000, "weight_kg": 45.0},
    ),
    (
        "РџРѕСЂС‚Р°С‚РёРІРЅР°СЏ СЃС‚Р°РЅС†РёСЏ EcoFlow River 2 Pro",
        "Р“РµРЅРµСЂР°С‚РѕСЂС‹ Рё РїРёС‚Р°РЅРёРµ",
        "EcoFlow",
        1200,
        3,
        {"capacity_wh": 768, "power_w": 800},
    ),
    # Р›РµСЃР° Рё РІС‹С€РєРё
    (
        "РЎС‚СЂРѕРёС‚РµР»СЊРЅС‹Рµ Р»РµСЃР°, 2 СЃРµРєС†РёРё",
        "РЎС‚СЂРѕРёС‚РµР»СЊРЅС‹Рµ Р»РµСЃР°",
        "РЎС‚СЂРѕР№С‚РµС…",
        800,
        2,
        {"height_m": 4.0, "load_kg": 200},
    ),
    (
        "Р’С‹С€РєР°-С‚СѓСЂР° 6 Рј",
        "РЎС‚СЂРѕРёС‚РµР»СЊРЅС‹Рµ Р»РµСЃР°",
        "РЎС‚СЂРѕР№С‚РµС…",
        1500,
        1,
        {"height_m": 6.0, "load_kg": 150},
    ),
    (
        "РџРѕРґРјРѕСЃС‚Рё 3 Рј",
        "РЎС‚СЂРѕРёС‚РµР»СЊРЅС‹Рµ Р»РµСЃР°",
        "РЎС‚СЂРѕР№С‚РµС…",
        500,
        2,
        {"height_m": 3.0, "load_kg": 150},
    ),
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
        print("РўР°Р±Р»РёС†С‹ РѕС‡РёС‰РµРЅС‹.")

    async with SessionLocal() as session:
        existing = await session.scalar(select(func.count()).select_from(Equipment))
        if existing:
            print(
                f"Р’ Р±Р°Р·Рµ СѓР¶Рµ {existing} РµРґРёРЅРёС† РѕР±РѕСЂСѓРґРѕРІР°РЅРёСЏ вЂ” РїСЂРѕРїСѓСЃРєР°СЋ (РёСЃРїРѕР»СЊР·СѓР№С‚Рµ --reset)."
            )
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
        admin = next(u for u in users if u.role == UserRole.admin)
        for title, category, brand, price, quantity, specs in EQUIPMENT:
            hourly = max(50, round(price / 8 / 10) * 10)
            item = Equipment(
                owner_id=admin.id,
                title=title,
                category=category,
                brand=brand,
                price_per_hour=Decimal(str(hourly)),
                price_per_day=Decimal(str(price)),
                min_hours=2,
                min_days=1,
                max_hours=24,
                max_days=30,
                quantity=quantity,
                buffer_minutes=30,
                lead_time_minutes=30,
                working_hours=WORKING_HOURS,
                timezone="Europe/Moscow",
                specs=specs,
                description=f"{category}. {brand}. Р”РѕСЃС‚СѓРїРЅРѕ РµРґРёРЅРёС†: {quantity}.",
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
                    picked_up_at=start,
                    returned_at=end,
                    quantity=qty,
                    billing_unit=BillingUnit.day,
                    unit_price=item.price_per_day,
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
                    billing_unit=BillingUnit.day,
                    unit_price=item.price_per_day,
                    total_price=item.price_per_day * qty * duration_days,
                    status=BookingStatus.confirmed,
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
            f"Р“РѕС‚РѕРІРѕ: {len(users)} РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№, {len(equipment)} РµРґРёРЅРёС† РѕР±РѕСЂСѓРґРѕРІР°РЅРёСЏ, "
            f"{len(bookings)} Р±СЂРѕРЅРµР№, {len(interactions)} РІР·Р°РёРјРѕРґРµР№СЃС‚РІРёР№."
        )
        print("РђРґРјРёРЅ: admin@example.com / admin12345")
        print("РђСЂРµРЅРґРѕРґР°С‚РµР»СЊ: owner@example.com / owner12345")
        print("РљР»РёРµРЅС‚: user@example.com / user12345")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="РѕС‡РёСЃС‚РёС‚СЊ С‚Р°Р±Р»РёС†С‹ РїРµСЂРµРґ РЅР°РїРѕР»РЅРµРЅРёРµРј",
    )
    args = parser.parse_args()
    asyncio.run(seed(reset=args.reset))


if __name__ == "__main__":
    main()
