"""Add user auth fields

Revision ID: a1b2c3d4e5f6
Revises: e3dbe026853e
Create Date: 2026-05-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "e3dbe026853e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column("role", sa.String(length=50), server_default="user", nullable=False)
        )
        batch_op.add_column(sa.Column("business_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False)
        )
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    op.execute(
        """
        UPDATE users
        SET name = split_part(email, '@', 1),
            password_hash = '',
            updated_at = created_at
        WHERE name IS NULL
        """
    )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("name", nullable=False)
        batch_op.alter_column("password_hash", nullable=False)
        batch_op.alter_column("updated_at", nullable=False)
        batch_op.create_index(batch_op.f("ix_users_business_id"), ["business_id"], unique=False)


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_business_id"))
        batch_op.drop_column("updated_at")
        batch_op.drop_column("is_active")
        batch_op.drop_column("business_id")
        batch_op.drop_column("role")
        batch_op.drop_column("password_hash")
        batch_op.drop_column("name")
