"""Simulation Dispatcher: mode に応じて Run or Swarm を作成・委譲する"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import async_session
from src.app.models.project import Project
from src.app.models.run import Run
from src.app.models.swarm import Swarm
from src.app.models.simulation import Simulation
from src.app.services.simulator import run_simulation, PROFILE_ROUNDS
from src.app.services.swarm_orchestrator import run_swarm
from src.app.services.pm_board_orchestrator import run_pm_board
from src.app.services.colony_factory import generate_colony_configs
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def dispatch_simulation(simulation_id: str) -> None:
    """Simulation レコードに基づいて適切な実行フローを起動する。"""
    logger.info(f"Dispatching simulation {simulation_id}")

    async with async_session() as session:
        try:
            sim = await session.get(Simulation, simulation_id)
            if not sim:
                logger.error(f"Simulation {simulation_id} not found")
                return

            sim.status = "running"
            sim.started_at = datetime.utcnow()
            await session.commit()

            # プロジェクト確保（prompt_text のみの場合は自動生成）
            project_id = await _ensure_project(session, sim)
            sim.project_id = project_id
            await session.commit()

            if sim.mode == "single":
                await _dispatch_single(session, sim)
            elif sim.mode in ("swarm", "hybrid"):
                await _dispatch_swarm(session, sim)
            elif sim.mode == "pm_board":
                await _dispatch_pm_board(session, sim)
            else:
                raise ValueError(f"Unknown mode: {sim.mode}")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"Simulation {simulation_id} failed: {error_msg}", exc_info=True)

            try:
                sim = await session.get(Simulation, simulation_id)
                if sim:
                    sim.status = "failed"
                    sim.error_message = error_msg[:500]
                    await session.commit()
            except Exception as db_err:
                logger.error(f"Failed to update simulation status: {db_err}")

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })


async def _ensure_project(session: AsyncSession, sim: Simulation) -> str:
    """プロジェクトがなければ自動作成する。"""
    if sim.project_id:
        project = await session.get(Project, sim.project_id)
        if project:
            # prompt_text をプロジェクトにも保存
            if sim.prompt_text and not project.prompt_text:
                project.prompt_text = sim.prompt_text
                await session.commit()
            return sim.project_id

    # 新規プロジェクト作成（プロンプトファースト）
    project = Project(
        id=str(uuid.uuid4()),
        name=f"Simulation {sim.id[:8]}",
        prompt_text=sim.prompt_text,
    )
    session.add(project)
    await session.commit()
    return project.id


async def _dispatch_single(session: AsyncSession, sim: Simulation) -> None:
    """Single モードの委譲: Run を作成して run_simulation() に委譲。"""
    total_rounds = PROFILE_ROUNDS.get(sim.execution_profile, 4)
    run = Run(
        id=str(uuid.uuid4()),
        project_id=sim.project_id,
        template_name=sim.template_name,
        execution_profile=sim.execution_profile,
        status="queued",
        total_rounds=total_rounds,
    )
    session.add(run)
    sim.run_id = run.id
    await session.commit()

    # SSE エイリアス登録
    sse_manager.add_alias(run.id, sim.id)

    try:
        await run_simulation(run.id, prompt_text=sim.prompt_text)

        sim_refreshed = await session.get(Simulation, sim.id)
        if sim_refreshed:
            sim_refreshed.status = "completed"
            sim_refreshed.completed_at = datetime.utcnow()
            await session.commit()

        await sse_manager.publish(sim.id, "simulation_completed", {
            "simulation_id": sim.id,
            "run_id": run.id,
        })
    finally:
        sse_manager.remove_alias(run.id)


async def _dispatch_swarm(session: AsyncSession, sim: Simulation) -> None:
    """Swarm/Hybrid モードの委譲: Swarm を作成して run_swarm() に委譲。"""
    profile_name = sim.execution_profile
    if sim.mode == "hybrid":
        # hybrid の場合、hybrid_ プレフィックスのプロファイルを使う
        hybrid_profile = f"hybrid_{sim.execution_profile}"
        try:
            generate_colony_configs(swarm_id="temp", profile_name=hybrid_profile)
            profile_name = hybrid_profile
        except ValueError:
            pass  # hybrid プロファイルがなければ通常のプロファイルを使用

    try:
        configs = generate_colony_configs(swarm_id="temp", profile_name=profile_name)
        colony_count = len(configs)
        round_count = configs[0].round_count if configs else 4
    except ValueError as e:
        raise ValueError(f"プロファイル設定エラー: {e}")

    swarm = Swarm(
        id=str(uuid.uuid4()),
        project_id=sim.project_id,
        template_name=sim.template_name,
        execution_profile=profile_name,
        status="queued",
        colony_count=colony_count,
        total_rounds=round_count,
    )
    session.add(swarm)
    sim.swarm_id = swarm.id
    sim.colony_count = colony_count
    await session.commit()

    # SSE エイリアス登録
    sse_manager.add_alias(swarm.id, sim.id)

    try:
        await run_swarm(swarm.id, prompt_text=sim.prompt_text)

        sim_refreshed = await session.get(Simulation, sim.id)
        if sim_refreshed:
            sim_refreshed.status = "completed"
            sim_refreshed.completed_at = datetime.utcnow()
            await session.commit()

        await sse_manager.publish(sim.id, "simulation_completed", {
            "simulation_id": sim.id,
            "swarm_id": swarm.id,
        })
    finally:
        sse_manager.remove_alias(swarm.id)


async def _dispatch_pm_board(session: AsyncSession, sim: Simulation) -> None:
    """PM Board モードの委譲: PMペルソナ並列分析 + チーフPM統合。"""
    # プロジェクト関連の文書テキストを取得
    document_text = ""
    if sim.project_id:
        from sqlalchemy import select
        from src.app.models.document import Document
        result = await session.execute(
            select(Document).where(Document.project_id == sim.project_id)
        )
        documents = result.scalars().all()
        document_text = "\n\n---\n\n".join(d.text_content for d in documents)

    pm_result = await run_pm_board(
        simulation_id=sim.id,
        prompt_text=sim.prompt_text,
        document_text=document_text,
    )

    # 結果をメタデータに保存
    sim_refreshed = await session.get(Simulation, sim.id)
    if sim_refreshed:
        sim_refreshed.status = "completed"
        sim_refreshed.completed_at = datetime.utcnow()
        sim_refreshed.metadata_json = pm_result
        await session.commit()

    await sse_manager.publish(sim.id, "simulation_completed", {
        "simulation_id": sim.id,
        "mode": "pm_board",
    })
