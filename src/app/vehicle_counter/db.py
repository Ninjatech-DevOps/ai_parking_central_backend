"""SQLite engine and session handling for the vehicle counter module.

Separate from ``src.app.db.session`` on purpose -- this module stores its data
in a standalone SQLite file inside the ``./data`` bind mount, so the file
persists across container rebuilds and can be copied off the host directly.

CONCURRENCY NOTE
----------------
SQLite allows many concurrent readers but only ONE writer. That is safe here
because ``scripts/entrypoint.sh`` starts uvicorn without ``--workers``, i.e. a
single process. If workers are ever added, multiple processes would contend for
the same file; WAL mode plus ``busy_timeout`` below makes that survivable but
not correct by construction.

The Celery workers do not mount ``./data`` and must never touch this database.
"""

import logging
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.app.core.config import settings

logger = logging.getLogger("ai_parking.vehicle_counter")


class VCBase(DeclarativeBase):
    """Declarative base for the vehicle counter SQLite database.

    Deliberately NOT ``src.app.db.base.Base``: that metadata is the Alembic
    autogenerate target for Postgres (``alembic/env.py`` sets
    ``target_metadata = Base.metadata``). Anything registered here must never
    end up in ``alembic/versions/``.
    """


vc_engine = create_async_engine(
    settings.vehicle_counter_db_url,
    echo=settings.DB_ECHO,
    # A writer that hits the lock waits instead of raising "database is locked".
    connect_args={"timeout": 30, "check_same_thread": False},
)


@event.listens_for(vc_engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):
    """Apply pragmas per connection.

    Registered on ``.sync_engine`` -- listening on the async engine object
    directly does not fire.
    """
    cursor = dbapi_conn.cursor()
    # WAL lets readers proceed during a write. Without it the default rollback
    # journal blocks readers and produces "database is locked" under even the
    # light concurrency of a polling counter page.
    cursor.execute("PRAGMA journal_mode=WAL")
    # Durable across process crashes under WAL, without an fsync on every tap.
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


vc_session_factory = async_sessionmaker(
    vc_engine, class_=AsyncSession, expire_on_commit=False
)


async def get_vc_db() -> AsyncSession:
    """Session dependency. Mirrors ``src.app.db.session.get_db`` semantics."""
    async with vc_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_vehicle_counter_db() -> None:
    """Create the data directory and table if absent. Called from lifespan."""
    db_path = Path(settings.VEHICLE_COUNTER_DB_PATH).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    from src.app.vehicle_counter import models  # noqa: F401  registers mappers

    async with vc_engine.begin() as conn:
        await conn.run_sync(VCBase.metadata.create_all)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await _add_missing_columns(conn)

    logger.info("Vehicle counter SQLite ready at %s", db_path)


# Columns added after the table first shipped. create_all() only creates
# missing tables, never missing columns, and this database is deliberately
# outside Alembic -- so tiny additive migrations are applied here instead.
_ADDED_COLUMNS = {
    "deleted_at": "DATETIME",
}


async def _add_missing_columns(conn) -> None:
    result = await conn.execute(text("PRAGMA table_info(vehicle_events)"))
    existing = {row[1] for row in result.fetchall()}

    for column, ddl_type in _ADDED_COLUMNS.items():
        if column in existing:
            continue
        await conn.execute(
            text(f"ALTER TABLE vehicle_events ADD COLUMN {column} {ddl_type}")
        )
        logger.info("Added column vehicle_events.%s", column)

    if "deleted_at" not in existing:
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_vehicle_events_deleted_at "
                "ON vehicle_events (deleted_at)"
            )
        )
