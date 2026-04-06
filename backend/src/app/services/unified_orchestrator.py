"""Unified Orchestrator: 3フェーズ統合シミュレーション

Society Pulse → Council Deliberation → Synthesis の3フェーズを順に実行し、
Decision Brief 付きの統合レポートを生成する。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from src.app.database import async_session
from src.app.models.kg_node import KGNode
from src.app.models.kg_edge import KGEdge
from src.app.models.simulation import Simulation
from src.app.services.phases.society_pulse import run_society_pulse
from src.app.services.phases.council_deliberation import run_council
from src.app.services.phases.synthesis import run_synthesis
from src.app.services.scenario_pair_status import refresh_scenario_pair_status
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def run_unified(simulation_id: str) -> None:
    """Unified モードのメインオーケストレーション。

    1つの async_session を開き、3フェーズに渡す。
    各フェーズ完了時にチェックポイント保存（session.commit）。
    """
    logger.info("Starting unified simulation %s", simulation_id)

    async with async_session() as session:
        sim = await session.get(Simulation, simulation_id)
        if not sim:
            logger.error("Simulation %s not found", simulation_id)
            return

        theme = sim.prompt_text

        try:
            # === KG データ取得（利用可能な場合） ===
            kg_entities: list[dict] = []
            kg_relations: list[dict] = []
            if sim.run_id:
                try:
                    nodes_result = await session.execute(
                        select(KGNode).where(KGNode.run_id == sim.run_id)
                    )
                    kg_nodes = nodes_result.scalars().all()
                    kg_entities = [
                        {
                            "name": n.label,
                            "type": n.node_type,
                            "description": n.description or "",
                            "importance_score": (n.properties or {}).get("importance_score", 0.5),
                            "aliases": n.aliases or [],
                            "source_chunk": (n.properties or {}).get("source_chunk", 0),
                        }
                        for n in kg_nodes
                    ]

                    edges_result = await session.execute(
                        select(KGEdge).where(KGEdge.run_id == sim.run_id)
                    )
                    kg_edges = edges_result.scalars().all()
                    # ノードIDからラベルへのマップを構築
                    node_id_to_label = {n.id: n.label for n in kg_nodes}
                    kg_relations = [
                        {
                            "source": node_id_to_label.get(e.source_node_id, ""),
                            "target": node_id_to_label.get(e.target_node_id, ""),
                            "type": e.relation_type or "related",
                            "evidence": e.evidence_text or "",
                            "confidence": e.confidence or 0.5,
                        }
                        for e in kg_edges
                    ]

                    if kg_entities:
                        logger.info(
                            "Loaded KG data: %d entities, %d relations",
                            len(kg_entities), len(kg_relations),
                        )
                except Exception as e:
                    logger.warning("Failed to load KG data, proceeding without: %s", e)

            # === Phase 1: Society Pulse ===
            await sse_manager.publish(simulation_id, "unified_phase_changed", {
                "phase": "society_pulse",
                "index": 1,
                "total": 3,
            })

            pulse = await run_society_pulse(
                session, sim, theme,
                kg_entities=kg_entities or None,
                kg_relations=kg_relations or None,
            )

            # チェックポイント保存
            sim.metadata_json = {
                **dict(sim.metadata_json or {}),
                "pulse_result": {
                    "aggregation": pulse.aggregation,
                    "evaluation": pulse.evaluation,
                    "usage": pulse.usage,
                },
            }
            await session.commit()

            # === Phase 2: Council Deliberation ===
            await sse_manager.publish(simulation_id, "unified_phase_changed", {
                "phase": "council",
                "index": 2,
                "total": 3,
            })

            council = await run_council(
                session, sim, pulse, theme,
                kg_entities=kg_entities or None,
                kg_relations=kg_relations or None,
            )

            sim.metadata_json = {
                **dict(sim.metadata_json or {}),
                "council_result": {
                    "participants": council.participants,
                    "devil_advocate_summary": council.devil_advocate_summary,
                    "usage": council.usage,
                },
            }
            await session.commit()

            # === Phase 3: Synthesis ===
            await sse_manager.publish(simulation_id, "unified_phase_changed", {
                "phase": "synthesis",
                "index": 3,
                "total": 3,
            })

            # Council で進化したKGがあればそちらを優先
            synthesis_kg_entities = council.kg_entities if council.kg_entities else (kg_entities or None)
            synthesis_kg_relations = council.kg_relations if council.kg_relations else (kg_relations or None)

            synthesis = await run_synthesis(
                session, sim, pulse, council, theme,
                kg_entities=synthesis_kg_entities,
                kg_relations=synthesis_kg_relations,
                use_react=True,
            )

            # 最終結果保存
            sim.metadata_json = {
                **dict(sim.metadata_json or {}),
                "unified_result": {
                    "type": "unified",
                    "decision_brief": synthesis.decision_brief,
                    "agreement_score": synthesis.agreement_score,
                    "content": synthesis.content,
                    "sections": synthesis.sections,
                    "society_summary": {
                        "population_count": pulse.population_count,
                        "selected_count": len(pulse.agents),
                        "aggregation": pulse.aggregation,
                        "evaluation": pulse.evaluation,
                    },
                    "council": {
                        "participants": council.participants,
                        "rounds": council.rounds,
                        "synthesis": council.synthesis,
                        "devil_advocate_summary": council.devil_advocate_summary,
                    },
                },
            }
            sim.status = "completed"
            sim.completed_at = datetime.now(timezone.utc)
            await refresh_scenario_pair_status(session, sim.scenario_pair_id)
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_completed", {
                "simulation_id": simulation_id,
                "mode": "unified",
                "agreement_score": synthesis.agreement_score,
                "recommendation": synthesis.decision_brief.get("recommendation", ""),
            })

            logger.info("Unified simulation %s completed", simulation_id)

        except Exception as e:
            logger.error("Unified simulation %s failed: %s", simulation_id, e, exc_info=True)
            await session.rollback()
            sim.status = "failed"
            sim.error_message = f"{type(e).__name__}: {e}"[:500]
            await refresh_scenario_pair_status(session, sim.scenario_pair_id)
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })
