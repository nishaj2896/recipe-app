"""defer the unique check on category positions

Revision ID: b9c084a51e74
Revises: 8134395b3d5f
Create Date: 2026-10-20 14:44:37.687790
"""

from collections.abc import Sequence

revision: str = "b9c084a51e74"
down_revision: str | Sequence[str] | None = "8134395b3d5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
