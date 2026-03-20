"""Swarm Orchestrator: N個の Colony を並列実行し、結果を統合する"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.database import async_session
from src.app.models.colony import Colony
from src.app.models.document import Document
from src.app.models.run import Run
from src.app.models.swarm import Swarm
from src.app.models.template import Template
from src.app.services.colony_factory import ColonyConfig, generate_colony_configs
from src.app.services.simulator import SingleRunSimulator
from src.app.services.world_builder import build_world
from src.app.services.graph_projection import project_graph, compute_diff, save_graph_state
from src.app.services.claim_extractor import extract_claims
from src.app.services.claim_clusterer import cluster_claims
from src.app.services.aggregator import aggregate_clusters
from src.app.services.simulation_live_state import update_report_progress
from src.app.services.swarm_report_generator import generate_swarm_integrated_report
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def run_swarm(
    swarm_id: str,
    prompt_text: str = "",
    initial_world_state: dict | None = None,
    additional_context: str = "",
    return_result: bool = False,
) -> dict | None:
    """Swarm 全体を実行する（バックグラウンドタスク）。

    Args:
        initial_world_state: 指定時は世界構築フェーズをスキップ（Single の結果を再利用）
        additional_context: Single の Report テキスト等を各 Colony のプロンプトに追加注入
        return_result: True の場合、aggregation + integrated_report を dict で返す
    """
    logger.info(f"Starting swarm {swarm_id}")
    pipeline_result = None

    async with async_session() as session:
        try:
            swarm = await session.get(Swarm, swarm_id)
            if not swarm:
                logger.error(f"Swarm {swarm_id} not found")
                return None

            swarm.status = "running"
            swarm.started_at = datetime.now(timezone.utc)
            await session.commit()

            await sse_manager.publish(swarm_id, "swarm_started", {
                "swarm_id": swarm_id,
                "colony_count": swarm.colony_count,
                "profile": swarm.execution_profile,
            })

            # 文書取得
            result = await session.execute(
                select(Document).where(Document.project_id == swarm.project_id)
            )
            documents = result.scalars().all()
            document_text = "\n\n---\n\n".join(d.text_content for d in documents)

            # prompt_text のフォールバック
            if not prompt_text:
                from src.app.models.project import Project
                project = await session.get(Project, swarm.project_id)
                if project and project.prompt_text:
                    prompt_text = project.prompt_text

            if not document_text.strip() and not prompt_text.strip():
                raise ValueError("入力文書またはプロンプトが必要です")

            # additional_context を prompt_text に注入
            effective_prompt = prompt_text
            if additional_context:
                effective_prompt = f"{prompt_text}\n\n--- 前段階分析結果 ---\n{additional_context}"

            # テンプレート取得
            result = await session.execute(
                select(Template).where(Template.name == swarm.template_name)
            )
            template = result.scalar_one_or_none()
            template_prompts = template.prompts if template else {}

            # === 1. 世界構築（initial_world_state が渡された場合はスキップ） ===
            if initial_world_state is not None:
                world_state = initial_world_state
                await sse_manager.publish(swarm_id, "world_initialized", {
                    "entity_count": len(world_state.get("entities", [])),
                    "relation_count": len(world_state.get("relations", [])),
                })
            else:
                await sse_manager.publish(swarm_id, "phase_changed", {
                    "phase": "world_building",
                })

                # ダミー run_id を世界構築用に作成
                world_run_id = str(uuid.uuid4())
                world_run = Run(
                    id=world_run_id,
                    project_id=swarm.project_id,
                    template_name=swarm.template_name,
                    execution_profile=swarm.execution_profile,
                    status="running",
                    total_rounds=swarm.total_rounds,
                    started_at=datetime.now(timezone.utc),
                )
                session.add(world_run)
                await session.commit()

                world_state = await build_world(
                    session, world_run_id, document_text,
                    template_prompts.get("world_build", ""),
                    prompt_text=prompt_text,
                )
                await session.commit()

                await sse_manager.publish(swarm_id, "world_initialized", {
                    "entity_count": len(world_state.get("entities", [])),
                    "relation_count": len(world_state.get("relations", [])),
                })

            # === 2. Colony 設定生成 ===
            colony_configs = generate_colony_configs(
                swarm_id=swarm_id,
                profile_name=swarm.execution_profile,
                diversity_mode=swarm.diversity_mode,
            )

            # Colony レコード作成
            for config in colony_configs:
                # 各 Colony 用の Run を作成
                colony_run_id = str(uuid.uuid4())
                colony_run = Run(
                    id=colony_run_id,
                    project_id=swarm.project_id,
                    template_name=swarm.template_name,
                    execution_profile=swarm.execution_profile,
                    status="queued",
                    total_rounds=config.round_count,
                )
                session.add(colony_run)

                colony = Colony(
                    id=config.colony_id,
                    swarm_id=swarm_id,
                    run_id=colony_run_id,
                    colony_index=config.colony_index,
                    perspective_id=config.perspective_id,
                    perspective_label=config.perspective_label,
                    temperature=config.temperature,
                    prompt_variant=config.prompt_variant,
                    adversarial=config.adversarial,
                    status="queued",
                    total_rounds=config.round_count,
                )
                session.add(colony)

            await session.commit()

            await sse_manager.publish(swarm_id, "colonies_created", {
                "colonies": [
                    {
                        "colony_id": c.colony_id,
                        "perspective": c.perspective_label,
                        "temperature": c.temperature,
                        "adversarial": c.adversarial,
                    }
                    for c in colony_configs
                ],
            })

            # === 3. Colony 並列実行 ===
            await sse_manager.publish(swarm_id, "phase_changed", {
                "phase": "colony_execution",
            })

            sem = asyncio.Semaphore(settings.max_concurrent_colonies)

            async def run_colony(config: ColonyConfig) -> dict:
                async with sem:
                    return await _execute_single_colony(
                        swarm_id, config, world_state, template_prompts,
                        prompt_text=effective_prompt,
                    )

            colony_results = await asyncio.gather(
                *[run_colony(c) for c in colony_configs],
                return_exceptions=True,
            )

            # 結果収集
            successful_results = []
            for i, result in enumerate(colony_results):
                config = colony_configs[i]
                if isinstance(result, Exception):
                    logger.error(
                        f"Colony {config.colony_id} failed: {result}",
                        exc_info=result,
                    )
                    async with async_session() as s:
                        colony = await s.get(Colony, config.colony_id)
                        if colony:
                            colony.status = "failed"
                            colony.error_message = str(result)[:500]
                            await s.commit()
                else:
                    successful_results.append({
                        "colony_id": config.colony_id,
                        "colony_config": config,
                        **result,
                    })

                swarm_refreshed = await session.get(Swarm, swarm_id)
                if swarm_refreshed:
                    swarm_refreshed.completed_colonies = i + 1
                    await session.commit()

            if not successful_results:
                raise ValueError("全ての Colony が失敗しました")

            await sse_manager.publish(swarm_id, "colonies_completed", {
                "successful": len(successful_results),
                "failed": len(colony_results) - len(successful_results),
            })

            # === 4. 主張抽出 + 集約 ===
            await sse_manager.publish(swarm_id, "phase_changed", {
                "phase": "aggregation",
            })

            all_claims = await extract_claims(session, swarm_id, successful_results)
            clusters = await cluster_claims(session, swarm_id, all_claims)
            aggregation = await aggregate_clusters(
                session, swarm_id, clusters, successful_results,
            )
            await session.commit()

            await sse_manager.publish(swarm_id, "aggregation_completed", {
                "scenario_count": len(aggregation.get("scenarios", [])),
                "diversity_score": aggregation.get("diversity_score", 0),
            })

            # === 5. 統合レポート生成 ===
            await sse_manager.publish(swarm_id, "phase_changed", {
                "phase": "report_generation",
            })

            integrated_report = ""
            try:
                integrated_report = await generate_swarm_integrated_report(
                    session=session,
                    swarm_id=swarm_id,
                    prompt_text=prompt_text,
                    colony_results=successful_results,
                    colony_configs=colony_configs,
                    aggregation=aggregation,
                )
                # AggregationResult の metadata に統合レポートを追加
                from sqlalchemy.orm.attributes import flag_modified
                from src.app.models.aggregation_result import AggregationResult as AggModel
                agg_result = await session.execute(
                    select(AggModel).where(AggModel.swarm_id == swarm_id)
                )
                agg_record = agg_result.scalar_one_or_none()
                if agg_record:
                    meta = dict(agg_record.metadata_json or {})
                    meta["integrated_report"] = integrated_report
                    agg_record.metadata_json = meta
                    flag_modified(agg_record, "metadata_json")
                    await session.commit()
                    logger.info(f"Integrated report saved to AggregationResult metadata")

                await sse_manager.publish(swarm_id, "report_completed", {
                    "report_length": len(integrated_report),
                })
                await update_report_progress(
                    session,
                    swarm_id=swarm_id,
                    status="completed",
                    last_error="",
                )
                logger.info(f"Integrated report generated for swarm {swarm_id}: {len(integrated_report)} chars")
            except Exception as report_err:
                logger.error(f"Integrated report generation failed: {report_err}", exc_info=True)
                await sse_manager.publish(swarm_id, "report_failed", {
                    "error": str(report_err)[:200],
                })
                await update_report_progress(
                    session,
                    swarm_id=swarm_id,
                    status="failed",
                    last_error=str(report_err)[:200],
                )

            # === 完了 ===
            swarm_final = await session.get(Swarm, swarm_id)
            if swarm_final:
                swarm_final.status = "completed"
                swarm_final.completed_at = datetime.now(timezone.utc)
                await session.commit()

            await sse_manager.publish(swarm_id, "swarm_completed", {
                "swarm_id": swarm_id,
                "scenarios": aggregation.get("scenarios", []),
            })

            logger.info(f"Swarm {swarm_id} completed successfully")

            if return_result:
                pipeline_result = {
                    "aggregation": aggregation,
                    "integrated_report": integrated_report,
                    "colony_results": successful_results,
                    "colony_configs": colony_configs,
                }

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"Swarm {swarm_id} failed: {error_msg}", exc_info=True)

            try:
                swarm_err = await session.get(Swarm, swarm_id)
                if swarm_err:
                    swarm_err.status = "failed"
                    swarm_err.error_message = error_msg[:500]
                    await session.commit()
            except Exception as db_err:
                logger.error(f"Failed to update swarm status: {db_err}")

            await sse_manager.publish(swarm_id, "swarm_failed", {
                "swarm_id": swarm_id,
                "error": str(e),
            })

    return pipeline_result


async def _execute_single_colony(
    swarm_id: str,
    config: ColonyConfig,
    world_state: dict,
    template_prompts: dict,
    prompt_text: str = "",
) -> dict:
    """1つの Colony を実行する（独立セッション使用）。"""
    async with async_session() as session:
        colony = await session.get(Colony, config.colony_id)
        if colony:
            colony.status = "running"
            colony.started_at = datetime.now(timezone.utc)
            await session.commit()

        run_id = colony.run_id if colony else config.colony_id

        # Run ステータス更新
        run = await session.get(Run, run_id)
        if run:
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await session.commit()

        await sse_manager.publish(swarm_id, "colony_started", {
            "colony_id": config.colony_id,
            "perspective": config.perspective_label,
            "temperature": config.temperature,
        })

        # SingleRunSimulator で実行
        simulator = SingleRunSimulator(colony_config=config)
        result = await simulator.run(
            run_id=run_id,
            world_state=dict(world_state),  # コピーして独立性を保つ
            session=session,
            template_prompts=template_prompts,
            total_rounds=config.round_count,
            sse_channel=swarm_id,
            prompt_text=prompt_text,
        )

        # Colony 完了更新
        colony = await session.get(Colony, config.colony_id)
        if colony:
            colony.status = "completed"
            colony.completed_at = datetime.now(timezone.utc)
            colony.result_data = {
                "event_count": len(result.get("events", [])),
                "agent_count": len(result.get("agents", {}).get("agents", [])),
            }
            await session.commit()

        # Run 完了更新
        run = await session.get(Run, run_id)
        if run:
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            await session.commit()

        await sse_manager.publish(swarm_id, "colony_completed", {
            "colony_id": config.colony_id,
            "perspective": config.perspective_label,
            "event_count": len(result.get("events", [])),
        })

        return result
