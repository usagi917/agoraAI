"""シミュレーションオーケストレータ: 全体のフローを管理

SingleRunSimulator: Colony 単位の独立実行をサポート
run_simulation: 後方互換の単体実行エントリーポイント
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.database import async_session
from src.app.models.document import Document
from src.app.models.run import Run
from src.app.models.template import Template
from src.app.services.colony_factory import ColonyConfig
from src.app.services.world_builder import build_world
from src.app.services.agent_generator import generate_agents
from src.app.services.round_processor import process_round
from src.app.services.graph_projection import project_graph, compute_diff, save_graph_state
from src.app.services.report_generator import generate_report
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

PROFILE_ROUNDS = {
    "preview": 2,
    "standard": 4,
    "quality": 6,
}


class SingleRunSimulator:
    """Colony 単位のシミュレーション実行器。

    colony_config が指定された場合、視点注入と温度オーバーライドを適用する。
    cognitive_mode == "advanced" の場合、GameMaster + CognitiveAgent で実行する。
    """

    def __init__(self, colony_config: ColonyConfig | None = None):
        self.colony_config = colony_config

    async def run(
        self,
        run_id: str,
        world_state: dict,
        session: AsyncSession,
        template_prompts: dict,
        total_rounds: int,
        sse_channel: str | None = None,
        prompt_text: str = "",
        cognitive_mode: str = "legacy",
        stakeholder_seeds=None,
    ) -> dict:
        """事前構築済みの world_state を使ってシミュレーションを実行する。

        Returns:
            最終 world_state、全イベント、エージェント情報を含む dict
        """
        channel = sse_channel or run_id

        # エージェント生成（視点注入あり）
        agent_prompt = template_prompts.get("agent_generate", "")
        if self.colony_config:
            agent_prompt = self._inject_perspective(agent_prompt)

        agents = await generate_agents(
            session, run_id, world_state, agent_prompt,
            prompt_text=prompt_text,
            stakeholder_seeds=stakeholder_seeds,
        )
        await session.commit()

        await sse_manager.publish(channel, "agents_built", {
            "run_id": run_id,
            "agent_count": len(agents.get("agents", [])),
            "colony_id": self.colony_config.colony_id if self.colony_config else None,
        })

        # advanced モード: CognitiveAgent を初期化
        cognitive_agents = []
        if cognitive_mode == "advanced":
            from src.app.services.cognition.cognitive_agent import CognitiveAgent

            for agent_profile in agents.get("agents", []):
                cognitive_agents.append(CognitiveAgent(run_id, agent_profile))

            await sse_manager.publish(channel, "cognitive_agents_initialized", {
                "run_id": run_id,
                "count": len(cognitive_agents),
            })

        # ラウンド実行
        prev_graph = project_graph(world_state)
        all_events = []
        rounds = self.colony_config.round_count if self.colony_config else total_rounds

        for round_num in range(1, rounds + 1):
            if cognitive_mode == "advanced" and cognitive_agents:
                # GameMaster モード
                from src.app.services.round_processor import process_round_advanced

                round_result = await process_round_advanced(
                    session, run_id, round_num, world_state,
                    cognitive_agents, all_events[-10:], channel,
                )
            else:
                # Legacy モード
                round_prompt = template_prompts.get("round_process", "")
                if self.colony_config:
                    round_prompt = self._inject_perspective(round_prompt)

                round_result = await process_round(
                    session, run_id, round_num, world_state, agents, round_prompt,
                    prompt_text=prompt_text,
                    sse_channel=channel,
                )
            await session.commit()

            world_state = round_result["updated_world_state"]
            round_data = round_result["round_result"]
            all_events.extend(round_data.get("events", []))

            # グラフ投影
            graph = project_graph(world_state)
            diff = compute_diff(prev_graph, graph)
            await save_graph_state(
                session, run_id, round_num, graph, diff,
                round_data.get("round_summary", ""),
            )
            await session.commit()
            prev_graph = graph

            # Run のラウンド進捗更新
            run = await session.get(Run, run_id)
            if run:
                run.current_round = round_num
                await session.commit()

            await sse_manager.publish(channel, "round_completed", {
                "run_id": run_id,
                "round": round_num,
                "total_rounds": rounds,
                "events": round_data.get("events", []),
                "summary": round_data.get("round_summary", ""),
                "colony_id": self.colony_config.colony_id if self.colony_config else None,
                "cognitive_mode": cognitive_mode,
            })

        return {
            "world_state": world_state,
            "events": all_events,
            "agents": agents,
        }

    def _inject_perspective(self, base_prompt: str) -> str:
        """Colony の視点をプロンプトに注入する。"""
        if not self.colony_config:
            return base_prompt
        injection = self.colony_config.system_injection.strip()
        if not injection:
            return base_prompt
        return f"{injection}\n\n{base_prompt}"


async def run_simulation(
    run_id: str,
    prompt_text: str = "",
    initial_world_state: dict | None = None,
    return_result: bool = False,
    evidence_mode: str = "prefer",
) -> dict | None:
    """シミュレーション全体を実行する（後方互換エントリーポイント）。

    Args:
        initial_world_state: 指定時は build_world() をスキップし、渡された world_state を使用
        return_result: True の場合、world_state/events/agents/report の dict を返す
    """
    logger.info(f"Starting simulation for run {run_id}")
    pipeline_result = None

    async with async_session() as session:
        try:
            run = await session.get(Run, run_id)
            if not run:
                logger.error(f"Run {run_id} not found")
                return None

            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await session.commit()

            await sse_manager.publish(run_id, "run_started", {
                "run_id": run_id,
                "profile": run.execution_profile,
                "total_rounds": run.total_rounds,
            })

            # 文書取得
            result = await session.execute(
                select(Document).where(Document.project_id == run.project_id)
            )
            documents = result.scalars().all()
            document_text = "\n\n---\n\n".join(d.text_content for d in documents)

            # prompt_text がプロジェクトにあればフォールバック
            if not prompt_text:
                from src.app.models.project import Project
                project = await session.get(Project, run.project_id)
                if project and project.prompt_text:
                    prompt_text = project.prompt_text

            if not document_text.strip() and not prompt_text.strip():
                raise ValueError("入力文書またはプロンプトが必要です")

            # テンプレート取得
            result = await session.execute(
                select(Template).where(Template.name == run.template_name)
            )
            template = result.scalar_one_or_none()
            template_prompts = template.prompts if template else {}

            # 世界構築（initial_world_state が渡された場合はスキップ）
            stakeholder_seeds = None
            if initial_world_state is not None:
                world_state = initial_world_state
                await sse_manager.publish(run_id, "world_initialized", {
                    "entity_count": len(world_state.get("entities", [])),
                    "relation_count": len(world_state.get("relations", [])),
                    "graph_diff": {},
                })
            else:
                # GraphRAG フェーズ（advanced モード時）
                knowledge_graph = None
                graphrag_config = settings.load_graphrag_config()

                if graphrag_config.get("enabled", False) and document_text.strip():
                    from src.app.services.graphrag.adapter import create_adapter

                    await sse_manager.publish(run_id, "graphrag_started", {
                        "message": "GraphRAGパイプラインを開始します",
                    })

                    adapter = create_adapter()
                    knowledge_graph = await adapter.build_knowledge_graph(
                        session, run_id, document_text,
                    )
                    await session.commit()

                    await sse_manager.publish(run_id, "graphrag_completed", {
                        "entity_count": len(knowledge_graph.entities),
                        "relation_count": len(knowledge_graph.relations),
                        "community_count": len(knowledge_graph.communities),
                    })

                world_state = await build_world(
                    session, run_id, document_text,
                    template_prompts.get("world_build", ""),
                    prompt_text=prompt_text,
                    knowledge_graph=knowledge_graph,
                )
                await session.commit()

                # ステークホルダーシード（GraphRAG 有効 + 十分なエンティティがある場合のみ）
                stakeholder_seeds = None
                if graphrag_config.get("enabled", False) and knowledge_graph is not None:
                    from src.app.services.graphrag.stakeholder_mapper import (
                        MIN_STAKEHOLDER_COUNT,
                        map_stakeholders,
                    )
                    try:
                        seeds = map_stakeholders(knowledge_graph)
                        if len(seeds) >= MIN_STAKEHOLDER_COUNT:
                            stakeholder_seeds = seeds
                        else:
                            logger.info(
                                "Insufficient stakeholder seeds (%d < %d), using generic agents",
                                len(seeds), MIN_STAKEHOLDER_COUNT,
                            )
                    except Exception:
                        logger.warning("map_stakeholders failed, falling back to generic agents")

            # 初期グラフ投影
            graph = project_graph(world_state)
            diff = compute_diff(None, graph)
            await save_graph_state(session, run_id, 0, graph, diff, "世界モデル初期化")
            await session.commit()

            if initial_world_state is None:
                await sse_manager.publish(run_id, "world_initialized", {
                    "entity_count": len(world_state.get("entities", [])),
                    "relation_count": len(world_state.get("relations", [])),
                    "graph_diff": diff,
                })

            # cognitive_mode 判定
            cognitive_config = settings.load_cognitive_config()
            cognitive_mode = cognitive_config.get("cognitive", {}).get("mode", settings.cognitive_mode)

            # SingleRunSimulator でラウンド実行
            simulator = SingleRunSimulator()
            result = await simulator.run(
                run_id=run_id,
                world_state=world_state,
                session=session,
                template_prompts=template_prompts,
                total_rounds=run.total_rounds,
                prompt_text=prompt_text,
                cognitive_mode=cognitive_mode,
                stakeholder_seeds=stakeholder_seeds,
            )

            # レポート生成
            run.status = "generating_report"
            await session.commit()

            report_sections = template_prompts.get("report_sections", None)
            await generate_report(
                session,
                run_id,
                result["world_state"],
                result["events"],
                result["agents"],
                report_sections,
                prompt_text=prompt_text,
                evidence_mode=evidence_mode,
            )
            await session.commit()

            # 完了
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            await session.commit()

            await sse_manager.publish(run_id, "run_completed", {
                "run_id": run_id,
                "total_rounds": run.total_rounds,
                "event_count": len(result["events"]),
            })

            logger.info(f"Simulation completed for run {run_id}")

            if return_result:
                # レポート内容を取得
                from src.app.models.report import Report as ReportModel
                report_result = await session.execute(
                    select(ReportModel).where(ReportModel.run_id == run_id)
                )
                report_record = report_result.scalar_one_or_none()
                pipeline_result = {
                    "world_state": result["world_state"],
                    "events": result["events"],
                    "agents": result["agents"],
                    "report_content": report_record.content if report_record else "",
                    "report_sections": report_record.sections if report_record else {},
                }

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"Simulation failed for run {run_id}: {error_msg}", exc_info=True)

            try:
                run = await session.get(Run, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = error_msg[:500]
                    await session.commit()
            except Exception as db_err:
                logger.error(f"Failed to update run status: {db_err}")

            await sse_manager.publish(run_id, "run_failed", {
                "run_id": run_id,
                "error": str(e),
            })

    return pipeline_result
