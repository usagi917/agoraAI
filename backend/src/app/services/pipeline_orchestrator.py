"""Pipeline Orchestrator: Single → Swarm → PM Board の3段階パイプライン実行"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from src.app.database import async_session
from src.app.models.run import Run
from src.app.models.swarm import Swarm
from src.app.models.simulation import Simulation
from src.app.services.simulator import run_simulation, PROFILE_ROUNDS
from src.app.services.swarm_orchestrator import run_swarm
from src.app.services.pm_board_orchestrator import run_pm_board
from src.app.services.colony_factory import generate_colony_configs
from src.app.services.final_report_generator import generate_final_report
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

# プロファイル別の Single ラウンド数
PIPELINE_SINGLE_ROUNDS = {
    "preview": 2,
    "standard": 4,
    "quality": 6,
}


async def run_pipeline(simulation_id: str) -> None:
    """3段階パイプライン（Single → Swarm → PM Board）を実行する。"""
    logger.info(f"Starting pipeline for simulation {simulation_id}")

    async with async_session() as session:
        try:
            sim = await session.get(Simulation, simulation_id)
            if not sim:
                logger.error(f"Simulation {simulation_id} not found")
                return

            # === Stage 1: Single ===
            await _update_pipeline_stage(session, sim, "single", {
                "single": "running", "swarm": "pending", "pm_board": "pending",
            })
            await sse_manager.publish(simulation_id, "pipeline_stage_started", {
                "stage": "single", "stage_index": 1,
            })

            single_result = await _run_stage_single(session, sim)

            await _update_stage_progress(session, sim, "single", "completed")
            await sse_manager.publish(simulation_id, "pipeline_stage_completed", {
                "stage": "single",
                "result_summary": {
                    "event_count": len(single_result.get("events", [])),
                    "has_report": bool(single_result.get("report_content")),
                },
            })

            # === Stage 1→2 変換 ===
            swarm_context = _build_swarm_context(single_result)

            # === Stage 2: Swarm ===
            await _update_pipeline_stage(session, sim, "swarm", None)
            await _update_stage_progress(session, sim, "swarm", "running")
            await sse_manager.publish(simulation_id, "pipeline_stage_started", {
                "stage": "swarm", "stage_index": 2,
            })

            swarm_result = await _run_stage_swarm(session, sim, swarm_context)

            await _update_stage_progress(session, sim, "swarm", "completed")
            await sse_manager.publish(simulation_id, "pipeline_stage_completed", {
                "stage": "swarm",
                "result_summary": {
                    "scenario_count": len(swarm_result.get("aggregation", {}).get("scenarios", [])),
                    "has_integrated_report": bool(swarm_result.get("integrated_report")),
                },
            })

            # === Stage 2→3 変換 ===
            pm_context = _build_pm_context(single_result, swarm_result)

            # === Stage 3: PM Board ===
            await _update_pipeline_stage(session, sim, "pm_board", None)
            await _update_stage_progress(session, sim, "pm_board", "running")
            await sse_manager.publish(simulation_id, "pipeline_stage_started", {
                "stage": "pm_board", "stage_index": 3,
            })

            pm_result = await _run_stage_pm_board(session, sim, pm_context)

            await _update_stage_progress(session, sim, "pm_board", "completed")
            await sse_manager.publish(simulation_id, "pipeline_stage_completed", {
                "stage": "pm_board",
                "result_summary": {
                    "section_count": len(pm_result.get("sections", {})),
                    "overall_confidence": pm_result.get("overall_confidence", 0),
                },
            })

            # === 最終統合レポート生成 ===
            sim_reporting = await session.get(Simulation, simulation_id)
            if sim_reporting:
                sim_reporting.status = "generating_report"
                await session.commit()

            await generate_final_report(
                session, sim, single_result, swarm_result, pm_result,
            )

            # 完了
            sim_final = await session.get(Simulation, simulation_id)
            if sim_final:
                sim_final.status = "completed"
                sim_final.completed_at = datetime.now(timezone.utc)
                sim_final.pipeline_stage = "completed"
                await session.commit()

            await sse_manager.publish(simulation_id, "pipeline_completed", {
                "simulation_id": simulation_id,
            })

            logger.info(f"Pipeline completed for simulation {simulation_id}")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"Pipeline {simulation_id} failed: {error_msg}", exc_info=True)

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


async def _update_pipeline_stage(
    session: AsyncSession, sim: Simulation, stage: str, progress: dict | None,
) -> None:
    sim_refreshed = await session.get(Simulation, sim.id)
    if sim_refreshed:
        sim_refreshed.pipeline_stage = stage
        if progress is not None:
            sim_refreshed.stage_progress = progress
            flag_modified(sim_refreshed, "stage_progress")
        await session.commit()


async def _update_stage_progress(
    session: AsyncSession, sim: Simulation, stage_key: str, status: str,
) -> None:
    sim_refreshed = await session.get(Simulation, sim.id)
    if sim_refreshed:
        progress = dict(sim_refreshed.stage_progress or {})
        progress[stage_key] = status
        sim_refreshed.stage_progress = progress
        flag_modified(sim_refreshed, "stage_progress")
        await session.commit()


async def _run_stage_single(session: AsyncSession, sim: Simulation) -> dict:
    """Stage 1: Single モード実行。"""
    total_rounds = PIPELINE_SINGLE_ROUNDS.get(sim.execution_profile, 4)
    run = Run(
        id=str(uuid.uuid4()),
        project_id=sim.project_id,
        template_name=sim.template_name,
        execution_profile=sim.execution_profile,
        status="queued",
        total_rounds=total_rounds,
    )
    session.add(run)
    sim_refreshed = await session.get(Simulation, sim.id)
    if sim_refreshed:
        sim_refreshed.run_id = run.id
    await session.commit()

    # SSE エイリアス登録
    sse_manager.add_alias(run.id, sim.id)

    try:
        result = await run_simulation(
            run.id,
            prompt_text=sim.prompt_text,
            return_result=True,
        )
        return result or {}
    finally:
        sse_manager.remove_alias(run.id)


async def _run_stage_swarm(
    session: AsyncSession, sim: Simulation, swarm_context: dict,
) -> dict:
    """Stage 2: Swarm モード実行。"""
    profile_name = sim.execution_profile

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
    sim_refreshed = await session.get(Simulation, sim.id)
    if sim_refreshed:
        sim_refreshed.swarm_id = swarm.id
        sim_refreshed.colony_count = colony_count
    await session.commit()

    # SSE エイリアス登録
    sse_manager.add_alias(swarm.id, sim.id)

    try:
        result = await run_swarm(
            swarm.id,
            prompt_text=sim.prompt_text,
            initial_world_state=swarm_context.get("world_state"),
            additional_context=swarm_context.get("additional_context", ""),
            return_result=True,
        )
        return result or {}
    finally:
        sse_manager.remove_alias(swarm.id)


async def _run_stage_pm_board(
    session: AsyncSession, sim: Simulation, pm_context: dict,
) -> dict:
    """Stage 3: PM Board モード実行。"""
    pm_result = await run_pm_board(
        simulation_id=sim.id,
        prompt_text=sim.prompt_text,
        document_text=pm_context.get("document_text", ""),
        scenario_candidates=pm_context.get("scenarios", []),
    )

    # 結果をメタデータに保存
    sim_refreshed = await session.get(Simulation, sim.id)
    if sim_refreshed:
        sim_refreshed.metadata_json = pm_result
        flag_modified(sim_refreshed, "metadata_json")
        await session.commit()

    return pm_result


def _build_swarm_context(single_result: dict) -> dict:
    """Single の結果を Swarm への入力コンテキストに変換する。"""
    world_state = single_result.get("world_state")
    report_content = single_result.get("report_content", "")

    # レポートが長すぎる場合は要約部分のみ抽出
    additional_context = report_content
    if len(additional_context) > 8000:
        additional_context = additional_context[:8000] + "\n\n[...レポート後半省略...]"

    return {
        "world_state": world_state,
        "additional_context": additional_context,
    }


def _build_pm_context(single_result: dict, swarm_result: dict) -> dict:
    """Single + Swarm の結果を PM Board への入力コンテキストに変換する。"""
    parts = []

    # Single のレポート
    report_content = single_result.get("report_content", "")
    if report_content:
        parts.append(f"## 因果分析レポート（Stage 1: Single Analysis）\n\n{report_content}")

    # Swarm の統合レポート
    integrated_report = swarm_result.get("integrated_report", "")
    if integrated_report:
        parts.append(f"## 多視点検証レポート（Stage 2: Swarm Analysis）\n\n{integrated_report}")

    # Swarm のシナリオ + メトリクス
    aggregation = swarm_result.get("aggregation", {})
    scenarios = aggregation.get("scenarios", [])
    if scenarios:
        scenario_text = "\n".join(
            f"- {s.get('description', '?')}: 確率 {s.get('probability', 0):.0%}"
            for s in scenarios[:10]
        )
        diversity = aggregation.get("diversity_score", 0)
        entropy = aggregation.get("entropy", 0)
        parts.append(
            f"## シナリオ確率分布\n\n{scenario_text}\n\n"
            f"多様性スコア: {diversity:.2f} / エントロピー: {entropy:.2f}"
        )

    document_text = "\n\n---\n\n".join(parts)

    # 長すぎる場合のフィルタリング
    if len(document_text) > 15000:
        document_text = document_text[:15000] + "\n\n[...コンテキスト後半省略...]"

    return {
        "document_text": document_text,
        "scenarios": scenarios,
    }
