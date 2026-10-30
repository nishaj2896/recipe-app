"""a recipe's long hands-off wait, for the plan ahead label

Revision ID: 9b1d4e7c2a60
Revises: 3f8a2c71d0b4
Create Date: 2026-10-30 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9b1d4e7c2a60"
down_revision: str | Sequence[str] | None = "3f8a2c71d0b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL until `recipe-app db sync` writes them (ADR-0009). The search reads
    # them only to show on cards, so a card simply has no label until then.
    op.add_column(
        "recipes", sa.Column("wait_minutes", sa.SmallInteger(), nullable=True)
    )
    op.add_column("recipes", sa.Column("wait_note", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_recipes_wait_in_range"),
        "recipes",
        "wait_minutes BETWEEN 60 AND 10080",
    )
    op.create_check_constraint(
        op.f("ck_recipes_wait_note_length"),
        "recipes",
        "length(wait_note) BETWEEN 1 AND 40",
    )
    op.create_check_constraint(
        op.f("ck_recipes_wait_has_note"),
        "recipes",
        "(wait_minutes IS NULL) = (wait_note IS NULL)",
    )


def downgrade() -> None:
    for name in ("wait_has_note", "wait_note_length", "wait_in_range"):
        op.drop_constraint(op.f(f"ck_recipes_{name}"), "recipes", type_="check")
    for column in ("wait_note", "wait_minutes"):
        op.drop_column("recipes", column)
