from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.app.database import (
    _apply_postgres_compatibility_migrations,
    _apply_sqlite_compatibility_migrations,
    _normalize_aware_datetime,
)
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


@pytest.mark.asyncio
async def test_sqlite_compatibility_migration_adds_simulation_scenario_pair_id(tmp_path):
    db_path = tmp_path / "legacy-simulations.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE simulations (
                    id VARCHAR(36) NOT NULL,
                    project_id VARCHAR(36),
                    mode VARCHAR(20) NOT NULL,
                    prompt_text TEXT NOT NULL,
                    template_name VARCHAR(100) NOT NULL,
                    execution_profile VARCHAR(20) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    error_message TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    run_id VARCHAR(36),
                    population_id VARCHAR(36),
                    pipeline_stage VARCHAR(20) DEFAULT 'pending',
                    stage_progress TEXT DEFAULT '{}',
                    seed INTEGER,
                    created_at DATETIME NOT NULL,
                    started_at DATETIME,
                    completed_at DATETIME,
                    PRIMARY KEY (id)
                )
                """
            )
        )
        await _apply_sqlite_compatibility_migrations(conn)

        columns = await conn.execute(text("PRAGMA table_info(simulations)"))
        assert "scenario_pair_id" in {row[1] for row in columns.fetchall()}

    await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_compatibility_migration_preserves_legacy_followups(tmp_path):
    db_path = tmp_path / "legacy-followups.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE followups (
                    id VARCHAR(36) NOT NULL,
                    simulation_id VARCHAR(36) NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    PRIMARY KEY (id)
                )
                """
            )
        )
        await conn.execute(
            text(
                "INSERT INTO followups (id, simulation_id, question, answer) "
                "VALUES ('f1', 's1', 'q1', 'a1')"
            )
        )

        await _apply_sqlite_compatibility_migrations(conn)

        rows = await conn.execute(text("SELECT question, answer FROM followups"))
        assert [tuple(row) for row in rows.fetchall()] == [("q1", "a1")]

    await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_compatibility_migration_preserves_simulation_foreign_keys_and_indexes(tmp_path):
    db_path = tmp_path / "legacy-simulations-fks.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.execute(text("CREATE TABLE projects (id VARCHAR(36) NOT NULL PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE runs (id VARCHAR(36) NOT NULL PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE populations (id VARCHAR(36) NOT NULL PRIMARY KEY)"))
        await conn.execute(
            text(
                """
                CREATE TABLE simulations (
                    id VARCHAR(36) NOT NULL,
                    project_id VARCHAR(36),
                    run_id VARCHAR(36),
                    population_id VARCHAR(36),
                    mode VARCHAR(20) NOT NULL,
                    prompt_text TEXT NOT NULL,
                    template_name VARCHAR(100) NOT NULL,
                    execution_profile VARCHAR(20) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    error_message TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    colony_count INTEGER NOT NULL DEFAULT 0,
                    deep_colony_count INTEGER NOT NULL DEFAULT 0,
                    pipeline_stage VARCHAR(20) DEFAULT 'pending',
                    stage_progress TEXT DEFAULT '{}',
                    seed INTEGER,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(project_id) REFERENCES projects(id),
                    FOREIGN KEY(run_id) REFERENCES runs(id),
                    FOREIGN KEY(population_id) REFERENCES populations(id)
                )
                """
            )
        )
        await conn.execute(
            text("CREATE INDEX ix_simulations_project_status ON simulations(project_id, status)")
        )

        await _apply_sqlite_compatibility_migrations(conn)

        fk_rows = (
            await conn.execute(text("PRAGMA foreign_key_list(simulations)"))
        ).fetchall()
        assert {row[2] for row in fk_rows} == {"projects", "runs", "populations"}

        index_rows = (await conn.execute(text("PRAGMA index_list(simulations)"))).fetchall()
        assert "ix_simulations_project_status" in {row[1] for row in index_rows}

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    """
                    INSERT INTO simulations (
                        id, project_id, run_id, population_id, mode, prompt_text, template_name,
                        execution_profile, status, error_message, metadata_json, colony_count,
                        deep_colony_count, pipeline_stage, stage_progress, seed, created_at
                    ) VALUES (
                        :id, :project_id, :run_id, :population_id, 'standard', '', '',
                        'standard', 'queued', '', '{}', 1, 0, 'pending', '{}', NULL, '2026-04-15 00:00:00'
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "project_id": str(uuid.uuid4()),
                    "run_id": str(uuid.uuid4()),
                    "population_id": str(uuid.uuid4()),
                },
            )

    await engine.dispose()


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def scalar(self):
        if not self._rows:
            return None
        row = self._rows[0]
        return row[0] if isinstance(row, tuple) else row


class _FakePostgresConn:
    def __init__(
        self,
        tables: list[str] | None = None,
        *,
        society_result_layer_length: int | None = None,
    ):
        self.executed_sql: list[str] = []
        self.tables = tables or ["simulations"]
        self.society_result_layer_length = society_result_layer_length

    async def run_sync(self, fn):
        tables = self.tables

        class _Dialect:
            @staticmethod
            def get_table_names(_conn):
                return tables

        class _SyncConn:
            dialect = _Dialect()

        return fn(_SyncConn())

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.executed_sql.append(sql)
        if (
            "SELECT character_maximum_length" in sql
            and "table_name = 'society_results'" in sql
        ):
            return _FakeResult([(self.society_result_layer_length,)])
        if "information_schema.columns" in sql:
            return _FakeResult(
                [
                    ("id",),
                    ("project_id",),
                    ("mode",),
                    ("prompt_text",),
                    ("template_name",),
                    ("execution_profile",),
                    ("status",),
                    ("error_message",),
                    ("metadata_json",),
                    ("run_id",),
                    ("population_id",),
                    ("pipeline_stage",),
                    ("stage_progress",),
                    ("seed",),
                    ("created_at",),
                    ("started_at",),
                    ("completed_at",),
                ]
            )
        return _FakeResult([])


@pytest.mark.asyncio
async def test_postgres_compatibility_migration_adds_simulation_scenario_pair_id():
    conn = _FakePostgresConn()

    await _apply_postgres_compatibility_migrations(conn)

    assert any(
        "ALTER TABLE simulations ADD COLUMN scenario_pair_id VARCHAR(36)" in sql
        for sql in conn.executed_sql
    )


@pytest.mark.asyncio
async def test_postgres_compatibility_migration_preserves_legacy_followups():
    conn = _FakePostgresConn(tables=["followups", "simulations"])

    await _apply_postgres_compatibility_migrations(conn)

    assert not any("DROP TABLE IF EXISTS followups" in sql for sql in conn.executed_sql)


@pytest.mark.asyncio
async def test_postgres_compatibility_migration_expands_society_result_layer_length():
    conn = _FakePostgresConn(
        tables=["society_results"],
        society_result_layer_length=20,
    )

    await _apply_postgres_compatibility_migrations(conn)

    assert any(
        "ALTER TABLE society_results ALTER COLUMN layer TYPE VARCHAR(50)" in sql
        for sql in conn.executed_sql
    )


@pytest.mark.asyncio
async def test_postgres_compatibility_migration_keeps_wide_society_result_layer_length():
    conn = _FakePostgresConn(
        tables=["society_results"],
        society_result_layer_length=50,
    )

    await _apply_postgres_compatibility_migrations(conn)

    assert not any(
        "ALTER TABLE society_results ALTER COLUMN layer TYPE VARCHAR(50)" in sql
        for sql in conn.executed_sql
    )


def test_simulation_model_excludes_legacy_swarm_columns():
    from src.app.models.simulation import Simulation

    columns = set(Simulation.__table__.columns.keys())

    assert "colony_count" not in columns
    assert "deep_colony_count" not in columns
    assert "swarm_id" not in columns


def test_normalize_aware_datetime_strips_timezone_for_db():
    value = datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc)

    normalized = _normalize_aware_datetime(value)

    assert normalized == datetime(2026, 3, 20, 9, 0)
    assert normalized.tzinfo is None
