"""add enterprise identity

Revision ID: d14f19a0a1e2
Revises: cbcaa8ac89c9
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d14f19a0a1e2"
down_revision: Union[str, Sequence[str], None] = "cbcaa8ac89c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "require_mfa",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "memberships",
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "memberships",
        sa.Column("scim_external_id", sa.String(length=255), nullable=True),
    )
    with op.batch_alter_table("memberships") as batch_op:
        batch_op.create_unique_constraint(
            "uq_memberships_org_scim_external_id",
            ["organization_id", "scim_external_id"],
        )
    op.create_table(
        "user_mfa",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("recovery_code_hashes", sa.JSON(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_invitations_org_email",
        "invitations",
        ["organization_id", "email"],
        unique=False,
    )
    op.create_index(
        "ix_invitations_token_hash",
        "invitations",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_index("ix_invitations_org_email", table_name="invitations")
    op.drop_table("invitations")
    op.drop_table("user_mfa")
    with op.batch_alter_table("memberships") as batch_op:
        batch_op.drop_constraint(
            "uq_memberships_org_scim_external_id",
            type_="unique",
        )
    op.drop_column("memberships", "scim_external_id")
    op.drop_column("memberships", "active")
    op.drop_column("organizations", "require_mfa")
