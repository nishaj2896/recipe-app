"""tags for search, food rules, the mood screen and pairings

Revision ID: 5c2e8a41b7d9
Revises: 9b1d4e7c2a60
Create Date: 2026-11-12 13:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5c2e8a41b7d9"
down_revision: str | Sequence[str] | None = "9b1d4e7c2a60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY = sa.text("'{}'::text[]")
ALLERGENS = (
    "peanuts",
    "tree-nuts",
    "dairy",
    "egg",
    "gluten",
    "soy",
    "sesame",
    "fish",
    "crustaceans",
    "molluscs",
    "mustard",
    "celery",
    "sulphites",
    "lupin",
)
CUISINES = (
    "north-indian",
    "south-indian",
    "east-indian",
    "west-indian",
    "indo-chinese",
    "street-food",
    "chinese",
    "japanese",
    "korean",
    "thai",
    "southeast-asian",
    "middle-eastern",
    "mediterranean",
    "italian",
    "french",
    "spanish-portuguese",
    "european",
    "american-british",
    "mexican-latin",
    "african-caribbean",
)
COURSES = (
    "breakfast",
    "snacks-starters",
    "soups",
    "salads",
    "mains",
    "rice-breads",
    "sides",
    "desserts",
    "drinks",
)
MOODS = (
    "spicy",
    "tangy",
    "sweet",
    "savoury",
    "creamy",
    "smoky",
    "fresh-herby",
    "comforting",
    "crispy",
    "sweet-sour",
    "light",
    "hearty",
)
WEATHER = (
    "cool-down",
    "rainy-day-cosy",
    "warming",
    "just-pleasant",
    "grey-gloomy",
    "cosy-night-in",
    "sticky-sluggish",
    "breezy-evening",
    "under-the-weather",
)


def _one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


def _subset_of(column: str, values: tuple[str, ...], most: int) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} <@ ARRAY[{listed}]::text[] AND cardinality({column}) <= {most}"


def _text_array(name: str) -> sa.Column[list[str]]:
    return sa.Column(
        name, postgresql.ARRAY(sa.Text()), server_default=EMPTY, nullable=False
    )


def upgrade() -> None:
    # Empty until `recipe-app db sync` writes them (ADR-0012). Nothing reads
    # them to filter yet, so an unsynced database only shows fewer details.
    op.add_column("ingredients", _text_array("allergens"))
    op.add_column(
        "ingredients",
        sa.Column("jain", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_ingredients_allergens_known"),
        "ingredients",
        _subset_of("allergens", ALLERGENS, 14),
    )

    op.add_column("recipes", sa.Column("cuisine", sa.Text(), nullable=True))
    for name in ("courses", "moods", "weather", "also_known_as", "allergens"):
        op.add_column("recipes", _text_array(name))
    op.add_column(
        "recipes",
        sa.Column(
            "jain", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    for name, condition in (
        ("cuisine_known", _one_of("cuisine", CUISINES)),
        ("courses_known", _subset_of("courses", COURSES, 2)),
        ("moods_known", _subset_of("moods", MOODS, 3)),
        ("weather_known", _subset_of("weather", WEATHER, 3)),
        ("aliases_count", "cardinality(also_known_as) <= 5"),
        ("allergens_known", _subset_of("allergens", ALLERGENS, 14)),
    ):
        op.create_check_constraint(op.f(f"ck_recipes_{name}"), "recipes", condition)

    op.create_table(
        "recipe_pairings",
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("paired_recipe_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "position BETWEEN 0 AND 3",
            name=op.f("ck_recipe_pairings_position_in_range"),
        ),
        sa.CheckConstraint(
            "paired_recipe_id <> recipe_id", name=op.f("ck_recipe_pairings_not_itself")
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_pairings_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paired_recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_pairings_paired_recipe_id_recipes"),
        ),
        sa.PrimaryKeyConstraint(
            "recipe_id", "position", name=op.f("pk_recipe_pairings")
        ),
        sa.UniqueConstraint(
            "recipe_id",
            "paired_recipe_id",
            name=op.f("uq_recipe_pairings_recipe_id_paired_recipe_id"),
        ),
    )
    op.create_index(
        "ix_recipe_pairings_paired_recipe_id", "recipe_pairings", ["paired_recipe_id"]
    )


def downgrade() -> None:
    op.drop_table("recipe_pairings")
    for name in (
        "allergens_known",
        "aliases_count",
        "weather_known",
        "moods_known",
        "courses_known",
        "cuisine_known",
    ):
        op.drop_constraint(op.f(f"ck_recipes_{name}"), "recipes", type_="check")
    for column in (
        "jain",
        "allergens",
        "also_known_as",
        "weather",
        "moods",
        "courses",
        "cuisine",
    ):
        op.drop_column("recipes", column)
    op.drop_constraint(
        op.f("ck_ingredients_allergens_known"), "ingredients", type_="check"
    )
    for column in ("jain", "allergens"):
        op.drop_column("ingredients", column)
