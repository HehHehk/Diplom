"""equipment check constraints

Revision ID: 113941cd5e17
Revises: b7ebac93e28d
Create Date: 2026-11-14 15:49:43.760999

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "113941cd5e17"
down_revision: Union[str, Sequence[str], None] = "b7ebac93e28d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_equipment_quantity_non_negative", "equipment", "quantity >= 0"
    )
    op.create_check_constraint(
        "ck_equipment_hour_price_non_negative",
        "equipment",
        "price_per_hour IS NULL OR price_per_hour >= 0",
    )
    op.create_check_constraint(
        "ck_equipment_day_price_non_negative",
        "equipment",
        "price_per_day IS NULL OR price_per_day >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_equipment_day_price_non_negative", "equipment", type_="check")
    op.drop_constraint("ck_equipment_hour_price_non_negative", "equipment", type_="check")
    op.drop_constraint("ck_equipment_quantity_non_negative", "equipment", type_="check")
