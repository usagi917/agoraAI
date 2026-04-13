"""Step 2: データモデル拡張テスト

TDD Red フェーズ:
- information_sources カラムの nullable 追加
- ValidationRecord の新カラム追加
- resolve_information_sources() フォールバック動作
- マイグレーション正常性
"""

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.app.database import (
    _apply_sqlite_compatibility_migrations,
    _apply_postgres_compatibility_migrations,
)


# ---------------------------------------------------------------------------
# ヘルパー: agent_profiles テーブルの CREATE SQL（values はSQLite予約語なので引用）
# ---------------------------------------------------------------------------

_CREATE_AGENT_PROFILES = """
CREATE TABLE agent_profiles (
    id VARCHAR(36) NOT NULL,
    population_id VARCHAR(36) NOT NULL,
    agent_index INTEGER NOT NULL,
    demographics JSON DEFAULT '{}',
    big_five JSON DEFAULT '{}',
    "values" JSON DEFAULT '{}',
    life_event TEXT NOT NULL DEFAULT '',
    contradiction TEXT NOT NULL DEFAULT '',
    information_source TEXT NOT NULL DEFAULT '',
    local_context TEXT NOT NULL DEFAULT '',
    hidden_motivation TEXT NOT NULL DEFAULT '',
    speech_style TEXT NOT NULL DEFAULT '',
    shock_sensitivity JSON DEFAULT '{}',
    llm_backend VARCHAR(50) NOT NULL DEFAULT 'openai',
    memory_summary TEXT NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id)
)
"""

_CREATE_VALIDATION_RECORDS = """
CREATE TABLE validation_records (
    id VARCHAR(36) NOT NULL,
    simulation_id VARCHAR(36) NOT NULL,
    theme_text VARCHAR(200) NOT NULL,
    theme_category VARCHAR(50) NOT NULL,
    simulated_distribution JSON NOT NULL,
    calibrated_distribution JSON,
    actual_distribution JSON,
    survey_source VARCHAR(200),
    survey_date VARCHAR(20),
    brier_score FLOAT,
    kl_divergence FLOAT,
    emd FLOAT,
    validated_at DATETIME,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id)
)
"""


# ---------------------------------------------------------------------------
# Red 1: AgentProfile.information_sources カラムの nullable 追加テスト
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sqlite_migration_adds_agent_profile_information_sources(tmp_path):
    """既存の agent_profiles テーブルに information_sources カラムが追加される"""
    db_path = tmp_path / "legacy_agent.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_AGENT_PROFILES))
        await _apply_sqlite_compatibility_migrations(conn)

        columns = await conn.execute(text("PRAGMA table_info(agent_profiles)"))
        col_names = {row[1] for row in columns.fetchall()}

    await engine.dispose()

    assert "information_sources" in col_names, (
        "information_sources カラムが agent_profiles に追加されていること"
    )


@pytest.mark.asyncio
async def test_sqlite_migration_information_sources_is_nullable(tmp_path):
    """information_sources カラムは NULL 許容（既存レコードが壊れない）"""
    db_path = tmp_path / "nullable_test.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_AGENT_PROFILES))
        # マイグレーション前にレコードを挿入
        await conn.execute(
            text(
                "INSERT INTO agent_profiles (id, population_id, agent_index, created_at) "
                "VALUES (:id, :pop, 0, '2026-01-01 00:00:00')"
            ),
            {"id": str(uuid.uuid4()), "pop": str(uuid.uuid4())},
        )
        await _apply_sqlite_compatibility_migrations(conn)

        result = await conn.execute(
            text("SELECT information_sources FROM agent_profiles")
        )
        rows = result.fetchall()

    await engine.dispose()

    assert len(rows) == 1
    assert rows[0][0] is None, "既存レコードの information_sources は NULL であること"


# ---------------------------------------------------------------------------
# Red 2: ValidationRecord 新カラム追加テスト
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sqlite_migration_adds_validation_record_new_columns(tmp_path):
    """validation_records テーブルに新カラムが追加される"""
    db_path = tmp_path / "legacy_val.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_VALIDATION_RECORDS))
        await _apply_sqlite_compatibility_migrations(conn)

        columns = await conn.execute(text("PRAGMA table_info(validation_records)"))
        col_names = {row[1] for row in columns.fetchall()}

    await engine.dispose()

    expected_new_cols = {
        "validation_status",
        "jsd",
        "theme_category_confidence",
        "theme_category_source",
        "survey_manifest_status",
    }
    missing = expected_new_cols - col_names
    assert not missing, f"validation_records に不足カラム: {missing}"


@pytest.mark.asyncio
async def test_sqlite_migration_validation_new_columns_are_nullable(tmp_path):
    """新カラムは全て NULL 許容（既存レコードが壊れない）"""
    db_path = tmp_path / "nullable_val.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_VALIDATION_RECORDS))
        # マイグレーション前にレコードを挿入
        await conn.execute(
            text(
                "INSERT INTO validation_records "
                "(id, simulation_id, theme_text, theme_category, simulated_distribution, created_at) "
                "VALUES (:id, :sim, 'test', 'economy', '{}', '2026-01-01 00:00:00')"
            ),
            {"id": str(uuid.uuid4()), "sim": str(uuid.uuid4())},
        )
        await _apply_sqlite_compatibility_migrations(conn)

        result = await conn.execute(
            text(
                "SELECT validation_status, jsd, theme_category_confidence, "
                "theme_category_source, survey_manifest_status FROM validation_records"
            )
        )
        rows = result.fetchall()

    await engine.dispose()

    assert len(rows) == 1
    row = rows[0]
    assert row[0] is None, "validation_status は NULL"
    assert row[1] is None, "jsd は NULL"
    assert row[2] is None, "theme_category_confidence は NULL"
    assert row[3] is None, "theme_category_source は NULL"
    assert row[4] is None, "survey_manifest_status は NULL"


# ---------------------------------------------------------------------------
# Red 3: resolve_information_sources() フォールバック動作テスト
# ---------------------------------------------------------------------------


def test_resolve_information_sources_returns_new_field_when_present():
    """新カラム information_sources が存在する場合はそれを返す"""
    from src.app.models.agent_profile import resolve_information_sources

    result = resolve_information_sources(
        information_sources=["NHK", "Twitter"],
        information_source="旧フィールド",
    )
    assert result == ["NHK", "Twitter"]


def test_resolve_information_sources_falls_back_to_legacy_string():
    """information_sources が None の場合は legacy の information_source を単一リストとして返す"""
    from src.app.models.agent_profile import resolve_information_sources

    result = resolve_information_sources(
        information_sources=None,
        information_source="テレビニュース",
    )
    assert result == ["テレビニュース"]


def test_resolve_information_sources_falls_back_to_default_when_both_empty():
    """どちらも空・None の場合はデフォルト値を返す"""
    from src.app.models.agent_profile import resolve_information_sources

    result = resolve_information_sources(
        information_sources=None,
        information_source="",
    )
    assert result == []


def test_resolve_information_sources_ignores_legacy_when_new_is_empty_list():
    """information_sources が空リスト（明示的に設定済み）の場合はそのまま返す"""
    from src.app.models.agent_profile import resolve_information_sources

    result = resolve_information_sources(
        information_sources=[],
        information_source="legacy value",
    )
    assert result == []


# ---------------------------------------------------------------------------
# Red 4: 既存レコードのデータマイグレーション正常性テスト
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sqlite_migration_copies_information_source_to_information_sources(tmp_path):
    """information_source の値が information_sources (JSON) にコピーされる"""
    db_path = tmp_path / "data_migration.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    agent_id = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_AGENT_PROFILES))
        # information_source に値が入っているレコードを挿入
        await conn.execute(
            text(
                "INSERT INTO agent_profiles "
                "(id, population_id, agent_index, information_source, created_at) "
                "VALUES (:id, :pop, 0, 'SNS・ソーシャルメディア', '2026-01-01 00:00:00')"
            ),
            {"id": agent_id, "pop": str(uuid.uuid4())},
        )
        await _apply_sqlite_compatibility_migrations(conn)

        result = await conn.execute(
            text("SELECT information_sources FROM agent_profiles WHERE id = :id"),
            {"id": agent_id},
        )
        row = result.fetchone()

    await engine.dispose()

    migrated = json.loads(row[0]) if row[0] else None
    assert migrated == ["SNS・ソーシャルメディア"], (
        "既存の information_source 値が information_sources にリスト形式でコピーされること"
    )


@pytest.mark.asyncio
async def test_sqlite_migration_skips_data_copy_if_information_source_is_empty(tmp_path):
    """information_source が空の場合はデータコピーをスキップして NULL のまま"""
    db_path = tmp_path / "data_migration_empty.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    agent_id = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_AGENT_PROFILES))
        await conn.execute(
            text(
                "INSERT INTO agent_profiles "
                "(id, population_id, agent_index, information_source, created_at) "
                "VALUES (:id, :pop, 0, '', '2026-01-01 00:00:00')"
            ),
            {"id": agent_id, "pop": str(uuid.uuid4())},
        )
        await _apply_sqlite_compatibility_migrations(conn)

        result = await conn.execute(
            text("SELECT information_sources FROM agent_profiles WHERE id = :id"),
            {"id": agent_id},
        )
        row = result.fetchone()

    await engine.dispose()

    assert row[0] is None, "information_source が空の場合は information_sources は NULL"


# ---------------------------------------------------------------------------
# Red 5: PostgreSQL 互換マイグレーション（fake conn）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakePostgresConnStep2:
    """PostgreSQL マイグレーション関数のテスト用フェイク接続"""

    def __init__(self, existing_tables, existing_columns_map):
        self.executed_sql: list[str] = []
        self._tables = existing_tables
        self._columns_map = existing_columns_map

    async def run_sync(self, fn):
        class _Dialect:
            def get_table_names(self_, _conn):
                return list(self._tables)

        class _SyncConn:
            dialect = _Dialect()

        return fn(_SyncConn())

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.executed_sql.append(sql)

        if "information_schema.columns" in sql:
            table = (params or {}).get("table", "")
            cols = self._columns_map.get(table, [])
            # conversation_logs の character_maximum_length クエリ
            if "character_maximum_length" in sql:
                return _FakeResult([(c, 255) for c in cols])
            return _FakeResult([(c,) for c in cols])

        return _FakeResult([])


@pytest.mark.asyncio
async def test_postgres_migration_adds_agent_profile_information_sources():
    """PostgreSQL マイグレーションが agent_profiles.information_sources を追加する"""
    conn = _FakePostgresConnStep2(
        existing_tables={"agent_profiles", "simulations", "conversation_logs"},
        existing_columns_map={
            "agent_profiles": [
                "id", "population_id", "agent_index", "demographics",
                "big_five", "values", "life_event", "contradiction",
                "information_source", "local_context", "hidden_motivation",
                "speech_style", "shock_sensitivity", "llm_backend",
                "memory_summary", "created_at",
            ],
            "simulations": ["id", "seed", "scenario_pair_id"],
            "conversation_logs": ["id", "participant_role", "stance"],
        },
    )

    await _apply_postgres_compatibility_migrations(conn)

    assert any(
        "agent_profiles" in sql and "information_sources" in sql
        for sql in conn.executed_sql
    ), f"information_sources 追加 SQL が見つからない。実行 SQL: {conn.executed_sql}"


@pytest.mark.asyncio
async def test_postgres_migration_adds_validation_record_new_columns():
    """PostgreSQL マイグレーションが validation_records の新カラムを追加する"""
    conn = _FakePostgresConnStep2(
        existing_tables={"validation_records", "simulations", "conversation_logs"},
        existing_columns_map={
            "validation_records": [
                "id", "simulation_id", "theme_text", "theme_category",
                "simulated_distribution", "brier_score", "kl_divergence", "emd",
                "validated_at", "created_at",
            ],
            "simulations": ["id", "seed", "scenario_pair_id"],
            "conversation_logs": ["id", "participant_role", "stance"],
        },
    )

    await _apply_postgres_compatibility_migrations(conn)

    for col in ["validation_status", "jsd", "theme_category_confidence",
                "theme_category_source", "survey_manifest_status"]:
        assert any(
            "validation_records" in sql and col in sql
            for sql in conn.executed_sql
        ), f"{col} 追加 SQL が見つからない。実行 SQL: {conn.executed_sql}"
