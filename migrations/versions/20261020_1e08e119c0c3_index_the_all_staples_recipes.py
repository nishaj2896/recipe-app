"""index the all-staples recipes

Revision ID: 1e08e119c0c3
Revises: 17d0315397da
Create Date: 2026-10-20 15:45:04.255569
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1e08e119c0c3"
down_revision: str | Sequence[str] | None = "17d0315397da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_recipes_all_staples"


def upgrade() -> None:
    # Partial: only the few recipes any pantry can cook, so it stays tiny.
    # Not CONCURRENTLY: only the sync writes recipes, and it doesn't run
    # during a migration (ADR-0005 rule 2).
    op.create_index(INDEX, "recipes", ["id"], postgresql_where=sa.text("all_staples"))


def downgrade() -> None:
    op.drop_index(INDEX, table_name="recipes")
