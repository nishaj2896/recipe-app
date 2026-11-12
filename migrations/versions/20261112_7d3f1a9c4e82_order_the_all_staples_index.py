"""order the all-staples index by the tier's sort key

Revision ID: 7d3f1a9c4e82
Revises: 5c2e8a41b7d9
Create Date: 2026-11-12 14:30:00.000000

The all-staples tier sorts by (total_minutes, id). On id alone, the
index gave no order, so Postgres had to read every all-staples recipe
and sort them. Once the recipes table grew past
min_parallel_table_scan_size (8 MB), a parallel Seq Scan became the
cheaper plan. Keyed on the sort columns, an ordered Index Only Scan
stops after one page of rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d3f1a9c4e82"
down_revision: str | Sequence[str] | None = "5c2e8a41b7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_recipes_all_staples"
ALL_STAPLES = sa.text("all_staples")


def upgrade() -> None:
    # Not CONCURRENTLY: only the sync writes recipes, and it doesn't run
    # during a migration (ADR-0005 rule 2).
    op.drop_index(INDEX, table_name="recipes")
    op.create_index(
        INDEX, "recipes", ["total_minutes", "id"], postgresql_where=ALL_STAPLES
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="recipes")
    op.create_index(INDEX, "recipes", ["id"], postgresql_where=ALL_STAPLES)
