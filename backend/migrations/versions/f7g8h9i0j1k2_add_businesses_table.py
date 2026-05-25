"""Add businesses table

Revision ID: f7g8h9i0j1k2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f7g8h9i0j1k2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "businesses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("phone_number", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("plan", sa.String(length=50), server_default="free", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="active", nullable=False),
        sa.Column("settings_json", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("businesses", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_businesses_slug"), ["slug"], unique=True)

    op.execute("UPDATE users SET business_id = NULL WHERE business_id IS NOT NULL")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_users_business_id_businesses",
            "businesses",
            ["business_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("fk_users_business_id_businesses", type_="foreignkey")

    with op.batch_alter_table("businesses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_businesses_slug"))

    op.drop_table("businesses")
