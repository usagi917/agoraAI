import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.app.database import _apply_sqlite_compatibility_migrations
from src.app.models.project import Project


@pytest.mark.asyncio
async def test_sqlite_compatibility_migration_adds_project_prompt_text(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE projects (
                    id VARCHAR(36) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id)
                )
                """
            )
        )
        await _apply_sqlite_compatibility_migrations(conn)

        columns = await conn.execute(text("PRAGMA table_info(projects)"))
        assert "prompt_text" in {row[1] for row in columns.fetchall()}

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        project = Project(
            id=str(uuid.uuid4()),
            name="debug",
            description="",
        )
        session.add(project)
        await session.commit()

    await engine.dispose()
