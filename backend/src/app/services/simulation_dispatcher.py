"""Simulation Dispatcher v2: プリセット駆動

旧9モードを normalize_mode() で5プリセットに正規化し、
baseline は専用オーケストレータ、それ以外は unified に委譲する。
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import async_session
from src.app.models.project import Project
from src.app.models.scenario_pair import ScenarioPair
from src.app.models.simulation import Simulation, normalize_mode
from src.app.services.baseline_orchestrator import run_baseline
from src.app.services.unified_orchestrator import run_unified
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


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
            sim.started_at = datetime.now(timezone.utc)
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
