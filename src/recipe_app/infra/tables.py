"""The database schema as SQLAlchemy Core tables (ADR-0005 rule 3).

Migrations own the real schema; these definitions must match them, and
tests/infra/test_migrations.py fails when they don't. Only the sync command
writes these tables.
"""

from collections.abc import Iterable
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)

from recipe_app.domain.catalog import MAX_ID_LENGTH, Diet, IngredientClass, StapleKind
from recipe_app.domain.recipe import MAX_TOTAL_MINUTES

# Every constraint gets a predictable name, so a later migration can drop it by name.
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def _one_of(column: str, values: Iterable[StrEnum]) -> str:
    """A CHECK that the column holds one of the enum's values."""
    listed = ", ".join(f"'{value.value}'" for value in values)
    return f"{column} IN ({listed})"


categories = Table(
    "categories",
    metadata,
    Column("id", String(MAX_ID_LENGTH), primary_key=True),
    Column("name", Text, nullable=False),
    Column("position", Integer, nullable=False, unique=True),
    Column("retired", Boolean, nullable=False),
    CheckConstraint("position > 0", name="position_positive"),
)

ingredients = Table(
    "ingredients",
    metadata,
    Column("id", String(MAX_ID_LENGTH), primary_key=True),
    Column("name", Text, nullable=False),
    # "class" is an SQL keyword, so the checks below quote it.
    Column("class", String(1), nullable=False),
    Column("kind", String(16)),
    Column("diet", String(16), nullable=False),
    Column("category_id", ForeignKey("categories.id"), nullable=False, index=True),
    Column("retired", Boolean, nullable=False),
    CheckConstraint(_one_of('"class"', IngredientClass), name="class_known"),
    CheckConstraint(_one_of("kind", StapleKind), name="kind_known"),
    CheckConstraint(_one_of("diet", Diet), name="diet_known"),
    # Staples have a kind and nothing else does (ADR-0002).
    CheckConstraint(
        f"(\"class\" = '{IngredientClass.STAPLE.value}') = (kind IS NOT NULL)",
        name="kind_iff_staple",
    ),
)

ingredient_search_terms = Table(
    "ingredient_search_terms",
    metadata,
    Column(
        "ingredient_id",
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("position", SmallInteger, primary_key=True),
    Column("term", Text, nullable=False),
    CheckConstraint("position >= 0", name="position_not_negative"),
)

recipes = Table(
    "recipes",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", Text, nullable=False),
    Column("prep_minutes", Integer, nullable=False),
    Column("cook_minutes", Integer, nullable=False),
    # Derived from the catalog; the sync recomputes both on every run (ADR rule 3).
    Column("diet", String(16), nullable=False),
    Column("all_staples", Boolean, nullable=False),
    CheckConstraint("prep_minutes >= 0", name="prep_not_negative"),
    CheckConstraint("cook_minutes >= 0", name="cook_not_negative"),
    CheckConstraint(
        f"prep_minutes + cook_minutes BETWEEN 1 AND {MAX_TOTAL_MINUTES}",
        name="total_in_range",
    ),
    CheckConstraint(_one_of("diet", Diet), name="diet_known"),
)

recipe_ingredients = Table(
    "recipe_ingredients",
    metadata,
    Column(
        "recipe_id",
        ForeignKey("recipes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    # The order a cook gathers them in; cards keep it.
    Column("position", SmallInteger, primary_key=True),
    Column("ingredient_id", ForeignKey("ingredients.id"), nullable=False),
    UniqueConstraint("recipe_id", "ingredient_id"),
    CheckConstraint("position >= 0", name="position_not_negative"),
    # The search's hot path: which recipes use any of these ingredients?
    Index(
        "ix_recipe_ingredients_ingredient_id_recipe_id",
        "ingredient_id",
        "recipe_id",
    ),
)

catalog_state = Table(
    "catalog_state",
    metadata,
    # Exactly one row: the catalog the data was last synced from.
    Column("singleton", Boolean, primary_key=True),
    Column("content_hash", String(64), nullable=False),
    Column("synced_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("singleton", name="one_row"),
)
