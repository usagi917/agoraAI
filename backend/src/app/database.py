from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.app.config import settings


class Base(DeclarativeBase):
    pass


# PostgreSQL uses asyncpg; SQLite uses aiosqlite (for local dev fallback)
engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _ensure_sqlite_database_dir() -> None:
    if not settings.is_sqlite:
        return

    db_path = make_url(settings.database_url).database
    if not db_path or db_path == ":memory:":
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


async def _get_sqlite_columns(conn: AsyncConnection, table_name: str) -> set[str]:
    result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


async def _apply_sqlite_compatibility_migrations(conn: AsyncConnection) -> None:
    existing_tables = await conn.run_sync(
        lambda sync_conn: set(sync_conn.dialect.get_table_names(sync_conn))
    )

    if "projects" in existing_tables:
        project_columns = await _get_sqlite_columns(conn, "projects")
        if "prompt_text" not in project_columns:
            await conn.execute(
                text("ALTER TABLE projects ADD COLUMN prompt_text TEXT NOT NULL DEFAULT ''")
            )

    if "simulations" in existing_tables:
        sim_columns = await _get_sqlite_columns(conn, "simulations")
        if "pipeline_stage" not in sim_columns:
            await conn.execute(
                text("ALTER TABLE simulations ADD COLUMN pipeline_stage VARCHAR(20) DEFAULT 'pending'")
            )
        if "stage_progress" not in sim_columns:
            await conn.execute(
                text("ALTER TABLE simulations ADD COLUMN stage_progress TEXT DEFAULT '{}'")
            )


async def init_db():
    _ensure_sqlite_database_dir()
    async with engine.begin() as conn:
        from src.app.models import _import_all_models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
        if settings.is_sqlite:
            await _apply_sqlite_compatibility_migrations(conn)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
