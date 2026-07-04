"""Simulation Dispatcher v2: プリセット駆動.

旧9モードを normalize_mode() で5プリセットに正規化し、
baseline は専用オーケストレータ、それ以外は unified に委譲する。
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from src.app.config import settings
from src.app.database import async_session, engine
from src.app.models.project import Project
from src.app.models.scenario_pair import ScenarioPair
from src.app.models.simulation import Simulation, normalize_mode
from src.app.services.baseline_orchestrator import run_baseline
from src.app.services.scenario_pair_status import refresh_scenario_pair_status
from src.app.services.unified_orchestrator import run_unified
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()
_STARTUP_RESUME_ADVISORY_LOCK_ID = 824319481507
_startup_resume_leader_conn: AsyncConnection | None = None


def _on_task_done(task: asyncio.Task) -> None:
    """Log unhandled exceptions from background simulation tasks."""
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        exc = task.exception()
        logger.error(
            "Background simulation task failed: %s",
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )


def spawn_simulation(simulation_id: str) -> None:
    """Launch a simulation in the background and keep a strong task reference."""
    task = asyncio.create_task(dispatch_simulation(simulation_id))
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)


def _supports_postgres_advisory_lock() -> bool:
    return make_url(settings.database_url).get_backend_name().startswith("postgresql")


async def _try_acquire_startup_resume_leadership() -> bool:
    """Elect one API process to perform startup resume.

    PostgreSQL advisory locks are session-scoped, so the leader connection is
    intentionally kept open until FastAPI shutdown. That prevents another
    worker that starts slightly later from re-reading the same running rows.
    """
    global _startup_resume_leader_conn

    if not _supports_postgres_advisory_lock():
        return True
    if _startup_resume_leader_conn is not None:
        return True

    conn = await engine.connect()
    try:
        result = await conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": _STARTUP_RESUME_ADVISORY_LOCK_ID},
        )
        acquired = bool(result.scalar())
        await conn.commit()
        if not acquired:
            await conn.close()
            return False

        _startup_resume_leader_conn = conn
        return True
    except Exception:
        await conn.close()
        raise


async def release_startup_resume_leadership() -> None:
    """Release the startup resume leader lock held by this process, if any."""
    global _startup_resume_leader_conn

    conn = _startup_resume_leader_conn
    if conn is None:
        return

    _startup_resume_leader_conn = None
    try:
        await conn.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": _STARTUP_RESUME_ADVISORY_LOCK_ID},
        )
        await conn.commit()
    finally:
        await conn.close()


async def resume_unfinished_simulations() -> int:
    """Resume simulations left in an active state after a dev-server restart.

    uvicorn --reload cancels in-process background tasks. The database can then
    still say "running" even though no Python task exists. Re-enqueueing active
    records on startup lets checkpointed orchestrators continue from the last
    persisted phase.
    """
    if not await _try_acquire_startup_resume_leadership():
        logger.info("Skipping startup simulation resume; another process is the resume leader")
        return 0

    async with async_session() as session:
        result = await session.execute(
            select(Simulation.id).where(
                Simulation.status.in_(["queued", "running", "generating_report"])
            )
        )
        simulation_ids = list(result.scalars().all())

    for simulation_id in simulation_ids:
        logger.info("Resuming unfinished simulation %s", simulation_id)
        spawn_simulation(simulation_id)

    return len(simulation_ids)


async def dispatch_simulation(simulation_id: str) -> None:
    """Simulation レコードに基づいて適切な実行フローを起動する。"""
    logger.info("Dispatching simulation %s", simulation_id)

    async with async_session() as session:
        try:
            sim = await session.get(Simulation, simulation_id)
            if not sim:
                logger.error("Simulation %s not found", simulation_id)
                return

            # モード正規化（旧モード → 新プリセット）
            sim.mode = normalize_mode(sim.mode)
            sim.status = "running"
            sim.started_at = datetime.now(UTC)
            await refresh_scenario_pair_status(session, sim.scenario_pair_id)
            await session.commit()

            # Decision Lab: scenario_pair_id があれば intervention_params を取得
            if sim.scenario_pair_id:
                pair = await session.get(ScenarioPair, sim.scenario_pair_id)
                if pair and pair.intervention_params:
                    meta = dict(sim.metadata_json) if sim.metadata_json else {}
                    meta["intervention_params"] = pair.intervention_params
                    sim.metadata_json = meta
                    await session.commit()

            # プロジェクト確保（prompt_text のみの場合は自動生成）
            project_id = await _ensure_project(session, sim)
            sim.project_id = project_id
            await session.commit()

            if sim.mode == "baseline":
                await run_baseline(sim.id)
            else:
                # quick, standard, deep, research は全て unified が処理
                await run_unified(sim.id)

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error("Simulation %s failed: %s", simulation_id, error_msg, exc_info=True)

            try:
                await session.rollback()
                sim = await session.get(Simulation, simulation_id)
                if sim:
                    sim.status = "failed"
                    sim.error_message = error_msg[:500]
                    await refresh_scenario_pair_status(session, sim.scenario_pair_id)
                    await session.commit()
            except Exception as db_err:
                logger.error("Failed to update simulation status: %s", db_err)

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })


async def _ensure_project(session: AsyncSession, sim: Simulation) -> str:
    """プロジェクトがなければ自動作成する。"""
    if sim.project_id:
        project = await session.get(Project, sim.project_id)
        if project:
            if sim.prompt_text and not project.prompt_text:
                project.prompt_text = sim.prompt_text
                await session.commit()
            return sim.project_id

    project = Project(
        id=str(uuid.uuid4()),
        name=f"Simulation {sim.id[:8]}",
        prompt_text=sim.prompt_text,
    )
    session.add(project)
    await session.commit()
    return project.id
