"""rank the search in postgres

Revision ID: 06a575c240a8
Revises: 1e08e119c0c3
Create Date: 2026-10-29 08:06:23.669291
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "06a575c240a8"
down_revision: str | Sequence[str] | None = "1e08e119c0c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEARCH_INDEX = "ix_recipe_ingredients_ingredient_id_recipe_id"


def upgrade() -> None:
    # NULL until `recipe-app db sync` writes them; the app refuses to start
    # while any recipe has no core_weight, so the deploy order (migrate,
    # sync, roll the pods) enforces itself (ADR-0007).
    op.add_column(
        "recipe_ingredients",
        sa.Column("weight", sa.SmallInteger(), nullable=True),
    )
    # Covering the weight lets the ranking query read only the index.
    op.drop_index(SEARCH_INDEX, table_name="recipe_ingredients")
    op.create_index(
        SEARCH_INDEX,
        "recipe_ingredients",
        ["ingredient_id", "recipe_id"],
        postgresql_include=["weight"],
    )
    op.create_check_constraint(
        op.f("ck_recipe_ingredients_weight_not_negative"),
        "recipe_ingredients",
        "weight >= 0",
    )
    op.add_column(
        "recipes",
        sa.Column("core_weight", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_recipes_core_weight_not_negative"), "recipes", "core_weight >= 0"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_recipes_core_weight_not_negative"), "recipes", type_="check"
    )
    op.drop_column("recipes", "core_weight")
    op.drop_constraint(
        op.f("ck_recipe_ingredients_weight_not_negative"),
        "recipe_ingredients",
        type_="check",
    )
    op.drop_index(SEARCH_INDEX, table_name="recipe_ingredients")
    op.create_index(SEARCH_INDEX, "recipe_ingredients", ["ingredient_id", "recipe_id"])
    op.drop_column("recipe_ingredients", "weight")
