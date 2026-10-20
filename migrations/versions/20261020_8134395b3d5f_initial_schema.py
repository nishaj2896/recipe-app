"""initial schema

Revision ID: 8134395b3d5f
Revises:
Create Date: 2026-10-20 11:14:15.233475
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8134395b3d5f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_state",
        sa.Column("singleton", sa.Boolean(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("singleton", name=op.f("ck_catalog_state_one_row")),
        sa.PrimaryKeyConstraint("singleton", name=op.f("pk_catalog_state")),
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "position > 0", name=op.f("ck_categories_position_positive")
        ),
        sa.CheckConstraint(
            "id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_categories_id_slug")
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name=op.f("ck_categories_name_not_blank")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("position", name=op.f("uq_categories_position")),
    )
    op.create_table(
        "recipes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("prep_minutes", sa.Integer(), nullable=False),
        sa.Column("cook_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "total_minutes",
            sa.Integer(),
            sa.Computed("prep_minutes + cook_minutes", persisted=True),
            nullable=False,
        ),
        sa.Column("diet", sa.Text(), nullable=False),
        sa.Column("all_staples", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "diet IN ('vegan', 'vegetarian', 'egg', 'non_veg')",
            name=op.f("ck_recipes_diet_known"),
        ),
        sa.CheckConstraint(
            "cook_minutes >= 0", name=op.f("ck_recipes_cook_not_negative")
        ),
        sa.CheckConstraint(
            "total_minutes BETWEEN 1 AND 1440",
            name=op.f("ck_recipes_total_in_range"),
        ),
        sa.CheckConstraint(
            "prep_minutes >= 0", name=op.f("ck_recipes_prep_not_negative")
        ),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_recipes_name_not_blank")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipes")),
    )
    op.create_table(
        "ingredients",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("class", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=True),
        sa.Column("diet", sa.Text(), nullable=False),
        sa.Column("category_id", sa.String(length=64), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_ingredients_id_slug")
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name=op.f("ck_ingredients_name_not_blank")
        ),
        sa.CheckConstraint(
            "diet IN ('vegan', 'vegetarian', 'egg', 'non_veg')",
            name=op.f("ck_ingredients_diet_known"),
        ),
        sa.CheckConstraint(
            "kind IN ('fresh', 'pantry')", name=op.f("ck_ingredients_kind_known")
        ),
        sa.CheckConstraint(
            "\"class\" IN ('A', 'B', 'S')", name=op.f("ck_ingredients_class_known")
        ),
        sa.CheckConstraint(
            "(\"class\" = 'S') = (kind IS NOT NULL)",
            name=op.f("ck_ingredients_kind_iff_staple"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_ingredients_category_id_categories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingredients")),
    )
    op.create_index(
        op.f("ix_ingredients_category_id"), "ingredients", ["category_id"], unique=False
    )
    op.create_table(
        "ingredient_search_terms",
        sa.Column("ingredient_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0",
            name=op.f("ck_ingredient_search_terms_position_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_ingredient_search_terms_ingredient_id_ingredients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "ingredient_id", "position", name=op.f("pk_ingredient_search_terms")
        ),
    )
    op.create_table(
        "recipe_ingredients",
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("ingredient_id", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_recipe_ingredients_position_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_recipe_ingredients_ingredient_id_ingredients"),
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_ingredients_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "recipe_id", "position", name=op.f("pk_recipe_ingredients")
        ),
        sa.UniqueConstraint(
            "recipe_id",
            "ingredient_id",
            name=op.f("uq_recipe_ingredients_recipe_id_ingredient_id"),
        ),
    )
    op.create_index(
        "ix_recipe_ingredients_ingredient_id_recipe_id",
        "recipe_ingredients",
        ["ingredient_id", "recipe_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recipe_ingredients_ingredient_id_recipe_id", table_name="recipe_ingredients"
    )
    op.drop_table("recipe_ingredients")
    op.drop_table("ingredient_search_terms")
    op.drop_index(op.f("ix_ingredients_category_id"), table_name="ingredients")
    op.drop_table("ingredients")
    op.drop_table("recipes")
    op.drop_table("categories")
    op.drop_table("catalog_state")
