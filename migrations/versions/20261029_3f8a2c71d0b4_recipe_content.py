"""recipe servings, amounts, steps and photos

Revision ID: 3f8a2c71d0b4
Revises: 06a575c240a8
Create Date: 2026-10-29 13:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f8a2c71d0b4"
down_revision: str | Sequence[str] | None = "06a575c240a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNITS = (
    "'g', 'kg', 'ml', 'l', 'tsp', 'tbsp', 'cup', 'small', 'medium', 'large', "
    "'small-head', 'bunch', 'piece', 'clove', 'sprig', 'slice', 'leaf', 'pinch', 'can'"
)


def upgrade() -> None:
    # Every new column is NULL until `recipe-app db sync` writes it (ADR-0008
    # rule 5); the search never reads them, so the deploy order is unchanged.
    op.add_column("recipes", sa.Column("serves", sa.SmallInteger(), nullable=True))
    op.add_column("recipes", sa.Column("image_file", sa.Text(), nullable=True))
    op.add_column("recipes", sa.Column("image_sha256", sa.String(64), nullable=True))
    op.add_column("recipes", sa.Column("image_alt", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_recipes_serves_in_range"), "recipes", "serves BETWEEN 1 AND 12"
    )
    op.create_check_constraint(
        op.f("ck_recipes_image_all_or_none"),
        "recipes",
        "(image_file IS NULL) = (image_sha256 IS NULL)"
        " AND (image_file IS NULL) = (image_alt IS NULL)",
    )

    op.add_column(
        "recipe_ingredients",
        sa.Column("amount", sa.Numeric(9, 3), nullable=True),
    )
    op.add_column("recipe_ingredients", sa.Column("unit", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_recipe_ingredients_amount_positive"),
        "recipe_ingredients",
        "amount > 0",
    )
    op.create_check_constraint(
        op.f("ck_recipe_ingredients_unit_known"),
        "recipe_ingredients",
        f"unit IN ({UNITS})",
    )
    op.create_check_constraint(
        op.f("ck_recipe_ingredients_amount_has_unit"),
        "recipe_ingredients",
        "(amount IS NULL) = (unit IS NULL)",
    )

    op.create_table(
        "recipe_steps",
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_recipe_steps_position_not_negative")
        ),
        sa.CheckConstraint(
            "length(text) BETWEEN 1 AND 400", name=op.f("ck_recipe_steps_text_length")
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_steps_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("recipe_id", "position", name=op.f("pk_recipe_steps")),
    )


def downgrade() -> None:
    op.drop_table("recipe_steps")
    for name in ("amount_has_unit", "unit_known", "amount_positive"):
        op.drop_constraint(
            op.f(f"ck_recipe_ingredients_{name}"), "recipe_ingredients", type_="check"
        )
    op.drop_column("recipe_ingredients", "unit")
    op.drop_column("recipe_ingredients", "amount")
    for name in ("image_all_or_none", "serves_in_range"):
        op.drop_constraint(op.f(f"ck_recipes_{name}"), "recipes", type_="check")
    for column in ("image_alt", "image_sha256", "image_file", "serves"):
        op.drop_column("recipes", column)
