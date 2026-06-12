"""add evidence governance

Revision ID: e25a30b1b2f3
Revises: d14f19a0a1e2
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e25a30b1b2f3"
down_revision: Union[str, Sequence[str], None] = "d14f19a0a1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column(
            "scan_status",
            sa.String(length=20),
            nullable=False,
            server_default="not_required",
        ),
    )
    op.add_column(
        "evidence",
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "legal_holds",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("released_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["released_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legal_holds_org_active",
        "legal_holds",
        ["organization_id", "released_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_legal_holds_org_active", table_name="legal_holds")
    op.drop_table("legal_holds")
    op.drop_column("evidence", "scanned_at")
    op.drop_column("evidence", "scan_status")
