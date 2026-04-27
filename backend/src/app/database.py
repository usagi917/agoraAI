from datetime import datetime, timezone
from pathlib import Path
import re

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session

from src.app.config import settings


class Base(DeclarativeBase):
    pass


# PostgreSQL uses asyncpg; SQLite uses aiosqlite (for local dev fallback)
engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_aware_datetime(value: object) -> object:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


@event.listens_for(AsyncSession.sync_session_class, "before_flush")
def _normalize_model_datetimes(session: Session, _flush_context, _instances) -> None:
    for obj in set(session.new).union(session.dirty):
        mapper = inspect(obj).mapper
        for attr in mapper.column_attrs:
            value = getattr(obj, attr.key, None)
            normalized = _normalize_aware_datetime(value)
            if normalized is not value:
                setattr(obj, attr.key, normalized)


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


async def _get_existing_tables(conn: AsyncConnection) -> set[str]:
    return await conn.run_sync(
        lambda sync_conn: set(sync_conn.dialect.get_table_names(sync_conn))
    )


async def _get_sqlite_table_sql(conn: AsyncConnection, table_name: str) -> str | None:
    result = await conn.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
        {"table_name": table_name},
    )
    rows = result.fetchall()
    if not rows:
        return None
    return rows[0][0]


async def _get_sqlite_index_sqls(conn: AsyncConnection, table_name: str) -> list[str]:
    result = await conn.execute(
        text(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = :table_name AND sql IS NOT NULL "
            "ORDER BY name"
        ),
        {"table_name": table_name},
    )
    return [row[0] for row in result.fetchall()]


def _split_sqlite_table_definitions(definitions_sql: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_single_quote = False
    in_double_quote = False
    index = 0

    while index < len(definitions_sql):
        char = definitions_sql[index]

        if char == "'" and not in_double_quote:
            current.append(char)
            if in_single_quote and index + 1 < len(definitions_sql) and definitions_sql[index + 1] == "'":
                current.append(definitions_sql[index + 1])
                index += 2
                continue
            in_single_quote = not in_single_quote
            index += 1
            continue

        if char == '"' and not in_single_quote:
            current.append(char)
            if in_double_quote and index + 1 < len(definitions_sql) and definitions_sql[index + 1] == '"':
                current.append(definitions_sql[index + 1])
                index += 2
                continue
            in_double_quote = not in_double_quote
            index += 1
            continue

        if not in_single_quote and not in_double_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
                index += 1
                continue

        current.append(char)
        index += 1

    if current:
        parts.append("".join(current).strip())

    return parts


def _sqlite_definition_name(definition_sql: str) -> str | None:
    match = re.match(r'\s*(?:"([^"]+)"|`([^`]+)`|\[([^\]]+)\]|(\S+))', definition_sql)
    if not match:
        return None
    return next(group for group in match.groups() if group is not None)


def _sqlite_relax_not_null_in_create_sql(create_sql: str, target_columns: set[str]) -> str:
    open_paren = create_sql.find("(")
    close_paren = create_sql.rfind(")")
    if open_paren == -1 or close_paren == -1 or close_paren <= open_paren:
        raise RuntimeError("Unexpected SQLite CREATE TABLE format for simulations")

    prefix = create_sql[:open_paren + 1]
    definitions_sql = create_sql[open_paren + 1:close_paren]
    suffix = create_sql[close_paren:]

    rebuilt_definitions: list[str] = []
    for definition in _split_sqlite_table_definitions(definitions_sql):
        name = _sqlite_definition_name(definition)
        if name in target_columns:
            definition = re.sub(r"\bNOT\s+NULL\b", "", definition, flags=re.IGNORECASE)
        rebuilt_definitions.append(definition.strip())

    return prefix + "\n    " + ",\n    ".join(rebuilt_definitions) + "\n" + suffix


async def _apply_sqlite_compatibility_migrations(conn: AsyncConnection) -> None:
    import json as _json

    existing_tables = await _get_existing_tables(conn)

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
        if "population_id" not in sim_columns:
            await conn.execute(
                text("ALTER TABLE simulations ADD COLUMN population_id VARCHAR(36)")
            )
        if "seed" not in sim_columns:
            await conn.execute(
                text("ALTER TABLE simulations ADD COLUMN seed INTEGER")
            )
        if "scenario_pair_id" not in sim_columns:
            await conn.execute(
                text("ALTER TABLE simulations ADD COLUMN scenario_pair_id VARCHAR(36)")
            )
        # legacy カラムの NOT NULL 制約を除去（SQLite はテーブル再作成が必要）
        await _sqlite_drop_not_null_legacy_sim_columns(conn, sim_columns)

    # --- agent_profiles: Step 2 スキーマ拡張 ---
    if "agent_profiles" in existing_tables:
        ap_columns = await _get_sqlite_columns(conn, "agent_profiles")
        if "information_sources" not in ap_columns:
            await conn.execute(
                text("ALTER TABLE agent_profiles ADD COLUMN information_sources JSON")
            )
            # データマイグレーション: 空でない information_source → information_sources
            result = await conn.execute(
                text(
                    "SELECT id, information_source FROM agent_profiles "
                    "WHERE information_source IS NOT NULL AND information_source != ''"
                )
            )
            rows = result.fetchall()
            for row_id, src in rows:
                await conn.execute(
                    text(
                        "UPDATE agent_profiles SET information_sources = :val WHERE id = :id"
                    ),
                    {"val": _json.dumps([src], ensure_ascii=False), "id": row_id},
                )

    # --- agent_profiles: 二層メモリカラム追加 ---
    if "agent_profiles" in existing_tables:
        ap_columns2 = await _get_sqlite_columns(conn, "agent_profiles")
        if "rolling_summary" not in ap_columns2:
            await conn.execute(
                text("ALTER TABLE agent_profiles ADD COLUMN rolling_summary TEXT DEFAULT ''")
            )
        if "episodes" not in ap_columns2:
            await conn.execute(
                text("ALTER TABLE agent_profiles ADD COLUMN episodes JSON")
            )

    # --- validation_records: Step 2 スキーマ拡張 ---
    if "validation_records" in existing_tables:
        vr_columns = await _get_sqlite_columns(conn, "validation_records")
        for col_ddl in [
            ("jsd", "ALTER TABLE validation_records ADD COLUMN jsd FLOAT"),
            ("validation_status", "ALTER TABLE validation_records ADD COLUMN validation_status VARCHAR(50)"),
            ("theme_category_confidence", "ALTER TABLE validation_records ADD COLUMN theme_category_confidence FLOAT"),
            ("theme_category_source", "ALTER TABLE validation_records ADD COLUMN theme_category_source VARCHAR(50)"),
            ("survey_manifest_status", "ALTER TABLE validation_records ADD COLUMN survey_manifest_status VARCHAR(50)"),
        ]:
            col_name, ddl = col_ddl
            if col_name not in vr_columns:
                await conn.execute(text(ddl))


async def _sqlite_drop_not_null_legacy_sim_columns(conn: AsyncConnection, sim_columns: set[str]) -> None:
    """colony_count / deep_colony_count の NOT NULL 制約を SQLite のテーブル再作成で除去する。

    SQLite は ALTER COLUMN DROP NOT NULL をサポートしないため、
    旧テーブルをリネーム → 新テーブルを作成 → データコピー → 旧テーブル削除 の手順を踏む。
    対象カラムが存在しない場合や、すでに NOT NULL でない場合はスキップする。
    """
    legacy = {"colony_count", "deep_colony_count"}
    if not legacy.intersection(sim_columns):
        return

    result = await conn.execute(text("PRAGMA table_info(simulations)"))
    col_rows = result.fetchall()

    # notnull フィールドは PRAGMA table_info の index 3
    has_not_null = {row[1] for row in col_rows if row[1] in legacy and row[3] == 1}
    if not has_not_null:
        return

    all_col_names = [row[1] for row in col_rows]
    original_table_sql = await _get_sqlite_table_sql(conn, "simulations")
    if not original_table_sql:
        raise RuntimeError("Could not load original CREATE TABLE SQL for simulations")
    original_index_sqls = await _get_sqlite_index_sqls(conn, "simulations")
    rebuilt_table_sql = _sqlite_relax_not_null_in_create_sql(original_table_sql, has_not_null)

    await conn.execute(text("PRAGMA foreign_keys = OFF"))
    try:
        await conn.execute(text("ALTER TABLE simulations RENAME TO _simulations_legacy"))
        await conn.execute(text(rebuilt_table_sql))

        cols_csv = ", ".join(all_col_names)
        await conn.execute(
            text(f"INSERT INTO simulations ({cols_csv}) SELECT {cols_csv} FROM _simulations_legacy")
        )
        await conn.execute(text("DROP TABLE _simulations_legacy"))

        for index_sql in original_index_sqls:
            await conn.execute(text(index_sql))
    finally:
        await conn.execute(text("PRAGMA foreign_keys = ON"))


async def _get_postgres_columns(conn: AsyncConnection, table_name: str) -> set[str]:
    result = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :table"
        ),
        {"table": table_name},
    )
    return {row[0] for row in result.fetchall()}


async def _apply_postgres_compatibility_migrations(conn: AsyncConnection) -> None:
    from src.app.models.conversation_log import (
        CONVERSATION_LOG_PARTICIPANT_ROLE_MAX_LENGTH,
        CONVERSATION_LOG_STANCE_MAX_LENGTH,
    )

    existing_tables = await _get_existing_tables(conn)

    # --- simulations: スキーマ整合性 ---
    if "simulations" in existing_tables:
        sim_columns = await _get_postgres_columns(conn, "simulations")
        if "seed" not in sim_columns:
            await conn.execute(
                text("ALTER TABLE simulations ADD COLUMN seed INTEGER")
            )
        if "scenario_pair_id" not in sim_columns:
            await conn.execute(
                text("ALTER TABLE simulations ADD COLUMN scenario_pair_id VARCHAR(36)")
            )
        # 旧カラム（モデルから削除済み）の NOT NULL 制約を解除
        for legacy_col in ("colony_count", "deep_colony_count", "swarm_id"):
            if legacy_col in sim_columns:
                await conn.execute(
                    text(f"ALTER TABLE simulations ALTER COLUMN {legacy_col} DROP NOT NULL")
                )

    # --- agent_profiles: Step 2 スキーマ拡張 ---
    if "agent_profiles" in existing_tables:
        ap_columns = await _get_postgres_columns(conn, "agent_profiles")
        if "information_sources" not in ap_columns:
            await conn.execute(
                text("ALTER TABLE agent_profiles ADD COLUMN information_sources JSON")
            )
            # データマイグレーション: 空でない information_source → information_sources
            await conn.execute(
                text(
                    "UPDATE agent_profiles "
                    "SET information_sources = to_json(ARRAY[information_source]) "
                    "WHERE information_source IS NOT NULL AND information_source != ''"
                )
            )

    # --- agent_profiles: 二層メモリカラム追加 ---
    if "agent_profiles" in existing_tables:
        ap_columns2 = await _get_postgres_columns(conn, "agent_profiles")
        if "rolling_summary" not in ap_columns2:
            await conn.execute(
                text("ALTER TABLE agent_profiles ADD COLUMN rolling_summary TEXT DEFAULT ''")
            )
        if "episodes" not in ap_columns2:
            await conn.execute(
                text("ALTER TABLE agent_profiles ADD COLUMN episodes JSON")
            )

    # --- validation_records: Step 2 スキーマ拡張 ---
    if "validation_records" in existing_tables:
        vr_columns = await _get_postgres_columns(conn, "validation_records")
        for col_name, col_ddl in [
            ("jsd", "ALTER TABLE validation_records ADD COLUMN jsd FLOAT"),
            ("validation_status", "ALTER TABLE validation_records ADD COLUMN validation_status VARCHAR(50)"),
            ("theme_category_confidence", "ALTER TABLE validation_records ADD COLUMN theme_category_confidence FLOAT"),
            ("theme_category_source", "ALTER TABLE validation_records ADD COLUMN theme_category_source VARCHAR(50)"),
            ("survey_manifest_status", "ALTER TABLE validation_records ADD COLUMN survey_manifest_status VARCHAR(50)"),
        ]:
            if col_name not in vr_columns:
                await conn.execute(text(col_ddl))

    if "conversation_logs" not in existing_tables:
        return

    result = await conn.execute(
        text(
            """
            SELECT column_name, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'conversation_logs'
              AND column_name IN ('participant_role', 'stance')
            """
        )
    )
    column_lengths = {row[0]: row[1] for row in result.fetchall()}

    if (column_lengths.get("participant_role") or 0) < CONVERSATION_LOG_PARTICIPANT_ROLE_MAX_LENGTH:
        await conn.execute(
            text(
                f"ALTER TABLE conversation_logs ALTER COLUMN participant_role "
                f"TYPE VARCHAR({CONVERSATION_LOG_PARTICIPANT_ROLE_MAX_LENGTH})"
            )
        )

    if (column_lengths.get("stance") or 0) < CONVERSATION_LOG_STANCE_MAX_LENGTH:
        await conn.execute(
            text(
                f"ALTER TABLE conversation_logs ALTER COLUMN stance "
                f"TYPE VARCHAR({CONVERSATION_LOG_STANCE_MAX_LENGTH})"
            )
        )


async def init_db():
    _ensure_sqlite_database_dir()
    async with engine.begin() as conn:
        from src.app.models import _import_all_models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
        if settings.is_sqlite:
            await _apply_sqlite_compatibility_migrations(conn)
        elif make_url(settings.database_url).get_backend_name().startswith("postgresql"):
            await _apply_postgres_compatibility_migrations(conn)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
