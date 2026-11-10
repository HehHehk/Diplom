"""booking rules: owners, tariffs, disputes

Revision ID: 14312694e9b6
Revises: 21d73ce1d295
Create Date: 2026-11-10 22:07:11.283778

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "14312694e9b6"
down_revision: Union[str, Sequence[str], None] = "21d73ce1d295"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- справочник событий брони ---
    op.create_table(
        "booking_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column(
            "type",
            sa.Enum(
                "created",
                "picked_up",
                "returned",
                "cancelled",
                "no_show",
                "dispute_opened",
                "dispute_resolved",
                "penalty_applied",
                "compensated",
                name="event_type",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_booking_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            name=op.f("fk_booking_events_booking_id_bookings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_events")),
    )
    op.create_index(
        op.f("ix_booking_events_booking_id"), "booking_events", ["booking_id"], unique=False
    )

    # --- брони ---
    op.add_column("bookings", sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "bookings",
        sa.Column(
            "billing_unit",
            sa.Enum("hour", "day", name="billing_unit", native_enum=False, length=10),
            server_default="day",
            nullable=False,
        ),
    )
    op.add_column(
        "bookings",
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), server_default="0", nullable=False),
    )
    op.add_column("bookings", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "bookings",
        sa.Column(
            "cancelled_by",
            sa.Enum("user", "owner", "admin", "system", name="cancelled_by", native_enum=False, length=10),
            nullable=True,
        ),
    )
    op.add_column("bookings", sa.Column("cancellation_reason", sa.String(length=50), nullable=True))
    for column in ("penalty_amount", "refund_amount", "compensation_amount", "damage_amount"):
        op.add_column(
            "bookings",
            sa.Column(column, sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        )
    op.add_column(
        "bookings",
        sa.Column(
            "dispute_status",
            sa.Enum("none", "pending", "resolved", name="dispute_status", native_enum=False, length=20),
            server_default="none",
            nullable=False,
        ),
    )
    op.add_column("bookings", sa.Column("dispute_reason", sa.String(length=50), nullable=True))
    op.add_column("bookings", sa.Column("dispute_description", sa.Text(), nullable=True))
    op.add_column(
        "bookings",
        sa.Column(
            "resolution_outcome",
            sa.Enum(
                "client_fault",
                "owner_fault",
                "equipment_fault",
                "force_majeure",
                "no_fault",
                name="resolution_outcome",
                native_enum=False,
                length=30,
            ),
            nullable=True,
        ),
    )
    op.add_column("bookings", sa.Column("resolved_by", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "bookings", sa.Column("no_show_deadline", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("bookings", sa.Column("no_show_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "bookings", sa.Column("no_show_cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "bookings", sa.Column("appeal_deadline", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("ix_bookings_dispute_status"), "bookings", ["dispute_status"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_bookings_resolved_by_users"),
        "bookings",
        "users",
        ["resolved_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- оборудование ---
    op.add_column("equipment", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.add_column("equipment", sa.Column("price_per_hour", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "equipment",
        sa.Column("min_hours", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "equipment",
        sa.Column("min_days", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "equipment",
        sa.Column("max_hours", sa.Integer(), server_default="24", nullable=False),
    )
    op.add_column(
        "equipment",
        sa.Column("max_days", sa.Integer(), server_default="30", nullable=False),
    )
    op.add_column(
        "equipment",
        sa.Column("buffer_minutes", sa.Integer(), server_default="30", nullable=False),
    )
    op.add_column(
        "equipment",
        sa.Column("lead_time_minutes", sa.Integer(), server_default="30", nullable=False),
    )
    op.add_column(
        "equipment",
        sa.Column("working_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "equipment",
        sa.Column("timezone", sa.String(length=64), server_default="Europe/Moscow", nullable=False),
    )
    op.alter_column(
        "equipment", "price_per_day", existing_type=sa.NUMERIC(10, 2), nullable=True
    )
    op.create_index(op.f("ix_equipment_owner_id"), "equipment", ["owner_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_equipment_owner_id_users"),
        "equipment",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- пользователи ---
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(length=64), server_default="Europe/Moscow", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("timezone_source", sa.String(length=20), server_default="fallback", nullable=False),
    )
    for column in (
        "penalties_count",
        "cancellations_count",
        "incidents_count",
        "damage_count",
        "disputes_open",
        "disputes_total_30d",
        "disputes_rejected_30d",
    ):
        op.add_column(
            "users", sa.Column(column, sa.Integer(), server_default="0", nullable=False)
        )
    op.add_column(
        "users",
        sa.Column("moderation_mode", sa.String(length=20), server_default="normal", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("is_abuser", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    # --- приведение существующих данных ---
    op.execute("UPDATE bookings SET status = 'confirmed' WHERE status = 'pending'")
    op.execute(
        """
        UPDATE bookings AS b
        SET unit_price = COALESCE(e.price_per_day, 0)
        FROM equipment AS e
        WHERE b.equipment_id = e.id AND b.unit_price = 0
        """
    )
    op.execute(
        """
        UPDATE equipment
        SET owner_id = (SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1)
        WHERE owner_id IS NULL
        """
    )

    # --- ограничения целостности ---
    op.create_check_constraint(
        "ck_equipment_price_present",
        "equipment",
        "price_per_hour IS NOT NULL OR price_per_day IS NOT NULL",
    )
    op.create_check_constraint("ck_equipment_min_hours_positive", "equipment", "min_hours > 0")
    op.create_check_constraint("ck_equipment_min_days_positive", "equipment", "min_days > 0")
    op.create_check_constraint("ck_equipment_hours_range", "equipment", "max_hours >= min_hours")
    op.create_check_constraint("ck_equipment_days_range", "equipment", "max_days >= min_days")


def downgrade() -> None:
    op.drop_constraint("ck_equipment_days_range", "equipment", type_="check")
    op.drop_constraint("ck_equipment_hours_range", "equipment", type_="check")
    op.drop_constraint("ck_equipment_min_days_positive", "equipment", type_="check")
    op.drop_constraint("ck_equipment_min_hours_positive", "equipment", type_="check")
    op.drop_constraint("ck_equipment_price_present", "equipment", type_="check")

    op.drop_column("users", "is_abuser")
    op.drop_column("users", "moderation_mode")
    op.drop_column("users", "disputes_rejected_30d")
    op.drop_column("users", "disputes_total_30d")
    op.drop_column("users", "disputes_open")
    op.drop_column("users", "damage_count")
    op.drop_column("users", "incidents_count")
    op.drop_column("users", "cancellations_count")
    op.drop_column("users", "penalties_count")
    op.drop_column("users", "timezone_source")
    op.drop_column("users", "timezone")

    op.drop_constraint(op.f("fk_equipment_owner_id_users"), "equipment", type_="foreignkey")
    op.drop_index(op.f("ix_equipment_owner_id"), table_name="equipment")
    op.alter_column("equipment", "price_per_day", existing_type=sa.NUMERIC(10, 2), nullable=False)
    op.drop_column("equipment", "timezone")
    op.drop_column("equipment", "working_hours")
    op.drop_column("equipment", "lead_time_minutes")
    op.drop_column("equipment", "buffer_minutes")
    op.drop_column("equipment", "max_days")
    op.drop_column("equipment", "max_hours")
    op.drop_column("equipment", "min_days")
    op.drop_column("equipment", "min_hours")
    op.drop_column("equipment", "price_per_hour")
    op.drop_column("equipment", "owner_id")

    op.drop_constraint(op.f("fk_bookings_resolved_by_users"), "bookings", type_="foreignkey")
    op.drop_index(op.f("ix_bookings_dispute_status"), table_name="bookings")
    for column in (
        "appeal_deadline",
        "no_show_cancelled_at",
        "no_show_at",
        "no_show_deadline",
        "resolved_at",
        "resolved_by",
        "resolution_outcome",
        "dispute_description",
        "dispute_reason",
        "dispute_status",
        "damage_amount",
        "compensation_amount",
        "refund_amount",
        "penalty_amount",
        "cancellation_reason",
        "cancelled_by",
        "cancelled_at",
        "unit_price",
        "billing_unit",
        "returned_at",
        "picked_up_at",
    ):
        op.drop_column("bookings", column)

    op.drop_index(op.f("ix_booking_events_booking_id"), table_name="booking_events")
    op.drop_table("booking_events")
