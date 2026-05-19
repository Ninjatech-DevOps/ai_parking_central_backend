"""add notification read tracking and device_online trigger type

Revision ID: a1b2c3d4e5f6
Revises: f3a1b7c9d402
Create Date: 2026-05-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f3a1b7c9d402"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add read tracking to notification_logs
    op.add_column(
        "notification_logs",
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "notification_logs",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_logs_user_unread",
        "notification_logs",
        ["user_id", "is_read"],
        postgresql_where=sa.text("is_read = false"),
    )

    # Add DEVICE_ONLINE to alert_trigger_type_enum
    # Must run outside transaction — ALTER TYPE ADD VALUE cannot run inside a transaction block
    op.execute("COMMIT")
    op.execute("ALTER TYPE alert_trigger_type_enum ADD VALUE IF NOT EXISTS 'DEVICE_ONLINE'")

    # Seed DEVICE_ONLINE alert rule (new transaction)
    op.execute("""
        INSERT INTO alert_rules (id, name, trigger_type, severity, is_active, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'Device Online',
            'DEVICE_ONLINE',
            'MEDIUM',
            true,
            now(),
            now()
        )
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM alert_rules WHERE trigger_type = 'DEVICE_ONLINE'")
    op.drop_index("ix_notification_logs_user_unread", table_name="notification_logs")
    op.drop_column("notification_logs", "read_at")
    op.drop_column("notification_logs", "is_read")
