"""defer the unique check on category positions

Revision ID: 17d0315397da
Revises: 8134395b3d5f
Create Date: 2026-10-20 19:24:41.055949
"""

from collections.abc import Sequence

from alembic import op

revision: str = "17d0315397da"
down_revision: str | Sequence[str] | None = "8134395b3d5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "uq_categories_position"


def upgrade() -> None:
    # Postgres 16 can't ALTER a unique constraint to deferrable; recreate it.
    op.drop_constraint(CONSTRAINT, "categories", type_="unique")
    op.create_unique_constraint(
        CONSTRAINT,
        "categories",
        ["position"],
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, "categories", type_="unique")
    op.create_unique_constraint(CONSTRAINT, "categories", ["position"])
