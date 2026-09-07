"""add content chunk embeddings

Revision ID: 5a65f68d9814
Revises: 3f0500e2bcfc
Create Date: 2026-09-01 01:16:12.000742
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "5a65f68d9814"
down_revision: Union[str, None] = "3f0500e2bcfc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_chunks",
        sa.Column(
            "embedding",
            Vector(1536),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "content_chunks",
        "embedding",
    )