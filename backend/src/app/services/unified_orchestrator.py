"""Unified Orchestrator: 3フェーズ統合シミュレーション

Society Pulse → Council Deliberation → Synthesis の3フェーズを順に実行し、
Decision Brief 付きの統合レポートを生成する。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from src.app.database import async_session
from src.app.models.agent_profile import AgentProfile
from src.app.models.kg_node import KGNode
from src.app.models.kg_edge import KGEdge
from src.app.models.simulation import Simulation
from src.app.models.social_edge import SocialEdge
from src.app.models.society_result import SocietyResult
from src.app.services.phases.society_pulse import SocietyPulseResult, run_society_pulse
from src.app.services.phases.council_deliberation import CouncilResult, run_council
from src.app.services.phases.synthesis import SynthesisResult, run_synthesis
from src.app.services.scenario_pair_status import refresh_scenario_pair_status
from src.app.services.society.representative_selector import select_representatives
from src.app.services.society import accuracy_config as _acc_flags
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

FRESH_PULSE_STALE_METADATA_KEYS = {
    "council_result",
    "unified_result",
    "society_result",
    "time_axis_result",
    "time_axis_error",
    "validation_summary",
}


def _agent_profile_to_dict(agent: AgentProfile) -> dict:
    return {
        "id": agent.id,
        "agent_index": agent.agent_index,
        "demographics": agent.demographics or {},
        "big_five": agent.big_five or {},
        "values": agent.values or {},
        "life_event": agent.life_event or "",
        "contradiction": agent.contradiction or "",
        "information_source": agent.information_source or "",
        "information_sources": agent.information_sources or None,
        "local_context": agent.local_context or "",
        "hidden_motivation": agent.hidden_motivation or "",
        "speech_style": agent.speech_style or "",
        "shock_sensitivity": agent.shock_sensitivity or {},
        "llm_backend": agent.llm_backend or "openai",
        "memory_summary": agent.memory_summary or "",
        "rolling_summary": agent.rolling_summary or "",
        "episodes": agent.episodes or [],
    }


async def _load_pulse_checkpoint(session, sim: Simulation, theme: str) -> SocietyPulseResult | None:
    metadata = dict(sim.metadata_json or {})
    pulse_data = dict(metadata.get("pulse_result") or {})
    if not pulse_data:
        return None

    result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim.id, SocietyResult.layer == "activation")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    activation_record = result.scalar_one_or_none()
    if not activation_record or not activation_record.phase_data:
        return None

    phase_data = activation_record.phase_data or {}
    responses = list(phase_data.get("responses") or [])
    agent_ids = [r.get("agent_id") for r in responses if r.get("agent_id")]

    agents_by_id: dict[str, AgentProfile] = {}
    if agent_ids:
        agents_result = await session.execute(
            select(AgentProfile).where(AgentProfile.id.in_(agent_ids))
        )
        agents_by_id = {agent.id: agent for agent in agents_result.scalars().all()}

    agents = [
        _agent_profile_to_dict(agents_by_id[agent_id])
        for agent_id in agent_ids
        if agent_id in agents_by_id
    ]

    representatives = pulse_data.get("representatives")
    if not representatives and agents and responses:
        representatives = await select_representatives(
            agents,
            responses,
            max_citizen_reps=6,
            max_experts=4,
            theme=theme,
        )

    return SocietyPulseResult(
        agents=agents,
        responses=responses,
        aggregation=pulse_data.get("aggregation") or phase_data.get("aggregation") or {},
        evaluation=pulse_data.get("evaluation") or {},
        representatives=list(representatives or []),
        usage=pulse_data.get("usage") or {},
        population_count=int(pulse_data.get("population_count") or len(agents)),
        validation_summary=metadata.get("validation_summary"),
    )


def _load_council_checkpoint(sim: Simulation) -> CouncilResult | None:
    council_data = dict((sim.metadata_json or {}).get("council_result") or {})
    if not council_data.get("rounds") or not council_data.get("synthesis"):
        return None
    return CouncilResult(
        participants=list(council_data.get("participants") or []),
        rounds=list(council_data.get("rounds") or []),
        synthesis=dict(council_data.get("synthesis") or {}),
        devil_advocate_summary=str(council_data.get("devil_advocate_summary") or ""),
        usage=dict(council_data.get("usage") or {}),
        kg_entities=council_data.get("kg_entities"),
        kg_relations=council_data.get("kg_relations"),
    )


def _load_synthesis_checkpoint(sim: Simulation) -> SynthesisResult | None:
    unified_data = dict((sim.metadata_json or {}).get("unified_result") or {})
    decision_brief = dict(unified_data.get("decision_brief") or {})
    content = unified_data.get("content")
    if not decision_brief or not isinstance(content, str):
        return None

    agreement_score = unified_data.get("agreement_score")
    if agreement_score is None:
        agreement_score = decision_brief.get("agreement_score", 0.0)

    try:
        agreement_score = float(agreement_score)
    except (TypeError, ValueError):
        agreement_score = 0.0

    return SynthesisResult(
        decision_brief=decision_brief,
        agreement_score=agreement_score,
        content=content,
        sections=dict(unified_data.get("sections") or {}),
    )


def _drop_stale_metadata_after_fresh_pulse(metadata: dict | None) -> dict:
    """Keep input metadata but discard checkpoints from phases after a fresh pulse."""
    return {
        key: value
        for key, value in dict(metadata or {}).items()
        if key not in FRESH_PULSE_STALE_METADATA_KEYS
    }


def _build_time_axis_base_responses(pulse: SocietyPulseResult) -> list[dict]:
    base_responses: list[dict] = []
    for idx, resp in enumerate(pulse.responses):
        enriched = dict(resp)
        if not enriched.get("agent_id") and idx < len(pulse.agents):
            enriched["agent_id"] = pulse.agents[idx].get("id")
        base_responses.append(enriched)
    return base_responses


async def _run_time_axis_if_enabled(
    session,
    sim: Simulation,
    pulse: SocietyPulseResult,
    theme: str,
) -> bool:
    if not _acc_flags.is_enabled("time_axis_orchestrator"):
        return False

    try:
        from src.app.services.society.time_axis_runner import run_time_axis_pipeline

        selected_agent_ids = {
            agent.get("id")
            for agent in pulse.agents
            if agent.get("id")
        }
        base_edges: list[tuple] = []
        if sim.population_id:
            edge_result = await session.execute(
                select(SocialEdge).where(SocialEdge.population_id == sim.population_id)
            )
            edge_rows = edge_result.scalars().all()
            base_edges = [
                (edge.agent_id, edge.target_id)
                for edge in edge_rows
                if not selected_agent_ids
                or (
                    edge.agent_id in selected_agent_ids
                    and edge.target_id in selected_agent_ids
                )
            ]

        time_axis_report = await run_time_axis_pipeline(
            simulation_id=sim.id,
            base_responses=_build_time_axis_base_responses(pulse),
            base_edges=base_edges,
            theme=theme,
            sse_manager=sse_manager,
        )
        metadata = dict(sim.metadata_json or {})
        metadata.pop("time_axis_error", None)
        metadata["time_axis_result"] = time_axis_report
        sim.metadata_json = metadata
        await session.commit()
        return True
    except Exception as time_axis_exc:
        logger.exception("time-axis pipeline failed for sim %s", sim.id)
        metadata = dict(sim.metadata_json or {})
        metadata.pop("time_axis_result", None)
        metadata["time_axis_error"] = (
            f"{type(time_axis_exc).__name__}: {time_axis_exc}"
        )[:500]
        sim.metadata_json = metadata
        await session.commit()
        return False


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
        scenario_pair_id = sim.scenario_pair_id

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
            pulse = await _load_pulse_checkpoint(session, sim, theme)
            if pulse:
                logger.info("Resuming unified simulation %s from pulse checkpoint", simulation_id)
            else:
                pulse_metadata = _drop_stale_metadata_after_fresh_pulse(sim.metadata_json)
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
                if pulse.validation_summary is not None:
                    pulse_metadata["validation_summary"] = pulse.validation_summary
                sim.metadata_json = {
                    **pulse_metadata,
                    "pulse_result": {
                        "aggregation": pulse.aggregation,
                        "evaluation": pulse.evaluation,
                        "usage": pulse.usage,
                        "representatives": pulse.representatives,
                        "population_count": pulse.population_count,
                        "validation_summary": pulse.validation_summary,
                    },
                }
                await session.commit()

            # === Phase 2: Council Deliberation ===
            council = _load_council_checkpoint(sim)
            council_from_checkpoint = council is not None
            if council:
                logger.info("Resuming unified simulation %s from council checkpoint", simulation_id)
            else:
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
                        "rounds": council.rounds,
                        "synthesis": council.synthesis,
                        "devil_advocate_summary": council.devil_advocate_summary,
                        "usage": council.usage,
                        "kg_entities": council.kg_entities,
                        "kg_relations": council.kg_relations,
                    },
                }
                await session.commit()

            # === Phase 3: Synthesis ===
            synthesis = _load_synthesis_checkpoint(sim) if council_from_checkpoint else None
            if synthesis:
                logger.info("Resuming unified simulation %s from synthesis checkpoint", simulation_id)
            else:
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
            time_axis_available = await _run_time_axis_if_enabled(
                session, sim, pulse, theme,
            )

            sim.status = "completed"
            sim.completed_at = datetime.now(timezone.utc)
            await refresh_scenario_pair_status(session, scenario_pair_id)
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_completed", {
                "simulation_id": simulation_id,
                "mode": "unified",
                "agreement_score": synthesis.agreement_score,
                "recommendation": synthesis.decision_brief.get("recommendation", ""),
                "time_axis_available": time_axis_available,
            })

            logger.info("Unified simulation %s completed", simulation_id)

        except Exception as e:
            logger.error("Unified simulation %s failed: %s", simulation_id, e, exc_info=True)
            await session.rollback()
            failed_sim = await session.get(Simulation, simulation_id)
            if failed_sim:
                failed_sim.status = "failed"
                failed_sim.error_message = f"{type(e).__name__}: {e}"[:500]
                await refresh_scenario_pair_status(session, scenario_pair_id)
                await session.commit()

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })
