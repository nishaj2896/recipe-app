"""enable pg_trgm for recipe search

Revision ID: 4a7c2e9d1b30
Revises: 9b1e6c3d2a57
Create Date: 2026-11-14 14:30:00.000000

Its own migration, ahead of the index that needs it (ADR-0012 rule 10).
pg_trgm is a trusted extension since Postgres 13, so the database owner
can create it on managed Postgres without superuser. Downgrade leaves it
installed: other objects may use it, and it costs nothing unused.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "4a7c2e9d1b30"
down_revision: str | Sequence[str] | None = "9b1e6c3d2a57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    pass
