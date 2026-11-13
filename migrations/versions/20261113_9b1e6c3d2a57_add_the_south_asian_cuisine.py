"""add the south-asian cuisine

Revision ID: 9b1e6c3d2a57
Revises: 7d3f1a9c4e82
Create Date: 2026-11-13 11:00:00.000000

Cuisine ids are append-only (ADR-0012 rule 1), so the CHECK gains one
value. Downgrading needs no recipe tagged south-asian: run the sync from
the previous release's data first, or the old CHECK cannot be added.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "9b1e6c3d2a57"
down_revision: str | Sequence[str] | None = "7d3f1a9c4e82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = (
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
NEW = (*OLD, "south-asian")
NAME = "ck_recipes_cuisine_known"


def _one_of(values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"cuisine IN ({listed})"


def _replace(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f(NAME), "recipes", type_="check")
    op.create_check_constraint(op.f(NAME), "recipes", _one_of(values))


def upgrade() -> None:
    _replace(NEW)


def downgrade() -> None:
    _replace(OLD)
