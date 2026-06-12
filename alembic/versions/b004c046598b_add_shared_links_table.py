"""add shared_links table

Revision ID: b004c046598b
Revises: a1c2d3e4f5a6
Create Date: 2026-06-12 10:30:55.099778

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'b004c046598b'
down_revision: Union[str, None] = 'a1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Create enum if not exists
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE shared_link_scope_type_enum AS ENUM ('CITY','TALUKA','VILLAGE','AREA','LOCATION','CAMERA'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    ))

    # Create table if not exists
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS shared_links (
            id UUID PRIMARY KEY,
            token VARCHAR(32) NOT NULL UNIQUE,
            name VARCHAR(200),
            scope_type shared_link_scope_type_enum NOT NULL,
            scope_id UUID,
            camera_ids TEXT,
            created_by_user_id UUID NOT NULL REFERENCES users(id),
            expires_at TIMESTAMPTZ,
            is_active BOOLEAN NOT NULL DEFAULT true,
            view_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    # Create index if not exists
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_shared_links_token ON shared_links (token)"
    ))


def downgrade() -> None:
    op.drop_table('shared_links')
    op.execute("DROP TYPE IF EXISTS shared_link_scope_type_enum")
