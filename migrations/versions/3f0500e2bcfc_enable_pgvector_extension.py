"""enable pgvector extension

Revision ID: 3f0500e2bcfc
Revises: 44413ba9c3cc
Create Date: 2026-08-31 22:22:30.280936

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f0500e2bcfc'
down_revision: Union[str, None] = '44413ba9c3cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute(
        "CREATE EXTENSION IF NOT EXISTS vector"
    )


def downgrade() -> None:
    op.execute(
        "DROP EXTENSION IF EXISTS vector"
    )
