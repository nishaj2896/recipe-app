"""recipe search names, with a trigram index

Revision ID: 6e1b8f3a5c72
Revises: 4a7c2e9d1b30
Create Date: 2026-11-14 14:31:00.000000

One row per recipe name and alias, as a search key, for recipe search
(ADR-0012 rule 10). Empty until the next `recipe-app db sync`, so search
finds nothing by name until then; the deck is unaffected.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6e1b8f3a5c72"
down_revision: str | Sequence[str] | None = "4a7c2e9d1b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_search_names",
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position BETWEEN 0 AND 5",
            name=op.f("ck_recipe_search_names_position_in_range"),
        ),
        sa.CheckConstraint(
            "text <> ''", name=op.f("ck_recipe_search_names_text_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_search_names_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "recipe_id", "position", name=op.f("pk_recipe_search_names")
        ),
    )
    op.create_index(
        "ix_recipe_search_names_text_trgm",
        "recipe_search_names",
        ["text"],
        postgresql_using="gin",
        postgresql_ops={"text": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_table("recipe_search_names")
