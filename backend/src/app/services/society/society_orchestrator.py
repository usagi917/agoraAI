"""Society オーケストレータ: Population→選抜→活性化→評価→結果保存"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from src.app.database import async_session
from src.app.models.population import Population
from src.app.models.agent_profile import AgentProfile
from src.app.models.social_edge import SocialEdge
from src.app.models.simulation import Simulation
from src.app.models.society_result import SocietyResult
from src.app.models.evaluation_result import EvaluationResult
from src.app.services.society.population_generator import (
    generate_population,
    get_default_population_size,
    validate_population_size,
)
from src.app.services.society.network_generator import generate_network
from src.app.services.society.agent_selector import select_agents
from src.app.services.society.activation_layer import run_activation
from src.app.services.society.evaluation import evaluate_society_simulation
from src.app.services.society.representative_selector import select_representatives
from src.app.services.society.meeting_layer import run_meeting
from src.app.services.society.meeting_report import generate_meeting_report
from src.app.services.society.memory_compressor import update_agent_memories
from src.app.services.society.graph_evolution import evolve_social_graph
from src.app.services.society.demographic_analyzer import analyze_demographics
from src.app.services.society.narrative_generator import generate_narrative
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def _get_or_create_population(
    session,
    population_id: str | None = None,
    count: int | None = None,
) -> tuple[str, list[dict]]:
    """既存の Population を取得するか、新規生成する。"""
    resolved_count = get_default_population_size() if count is None else validate_population_size(count)

    if population_id:
        pop = await session.get(Population, population_id)
        if pop and pop.status == "ready":
            result = await session.execute(
                select(AgentProfile).where(AgentProfile.population_id == population_id)
            )
            agents_db = result.scalars().all()
            if agents_db:
                agents = []
                for a in agents_db:
                    agents.append({
                        "id": a.id,
                        "population_id": a.population_id,
                        "agent_index": a.agent_index,
                        "demographics": a.demographics,
                        "big_five": a.big_five,
                        "values": a.values,
                        "life_event": a.life_event,
                        "contradiction": a.contradiction,
                        "information_source": a.information_source,
                        "local_context": a.local_context,
                        "hidden_motivation": a.hidden_motivation,
                        "speech_style": a.speech_style,
                        "shock_sensitivity": a.shock_sensitivity,
                        "llm_backend": a.llm_backend,
                        "memory_summary": a.memory_summary,
                    })
                return population_id, agents

    # 新規生成
    pop_id = str(uuid.uuid4())
    population = Population(
        id=pop_id,
        agent_count=resolved_count,
        generation_params={"count": resolved_count},
        status="generating",
    )
    session.add(population)
    await session.commit()

    agents = await generate_population(pop_id, resolved_count)

    # DB に保存
    for agent_data in agents:
        profile = AgentProfile(**agent_data)
        session.add(profile)

    population.status = "ready"
    await session.commit()

    return pop_id, agents


async def _save_network(session, agents: list[dict], population_id: str) -> None:
    """ネットワークを生成して保存する。"""
    edges = await generate_network(agents, population_id)
    for edge_data in edges:
        edge = SocialEdge(**edge_data)
        session.add(edge)
    await session.commit()


async def run_society(simulation_id: str) -> None:
    """Society モードのメインオーケストレーション。"""
    logger.info("Starting society simulation %s", simulation_id)

    async with async_session() as session:
        sim = await session.get(Simulation, simulation_id)
        if not sim:
            logger.error("Simulation %s not found", simulation_id)
            return

        theme = sim.prompt_text
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        try:
            # === Phase 1: Population ===
            await sse_manager.publish(simulation_id, "society_started", {
                "simulation_id": simulation_id,
                "theme": theme[:100],
            })

            pop_count = get_default_population_size()
            await sse_manager.publish(simulation_id, "population_status", {
                "status": "generating",
                "target_count": pop_count,
            })

            pop_id, agents = await _get_or_create_population(
                session, sim.population_id, pop_count,
            )
            sim.population_id = pop_id
            await session.commit()

            await sse_manager.publish(simulation_id, "population_status", {
                "status": "ready",
                "agent_count": len(agents),
                "population_id": pop_id,
            })

            # ネットワーク生成（バックグラウンド的に）
            await _save_network(session, agents, pop_id)

            # === Phase 2: Selection ===
            selected_agents = await select_agents(agents, theme, target_count=100)

            await sse_manager.publish(simulation_id, "society_selection_completed", {
                "selected_count": len(selected_agents),
                "total_population": len(agents),
            })

            # === Phase 3: Activation ===
            await sse_manager.publish(simulation_id, "society_activation_started", {
                "agent_count": len(selected_agents),
            })

            async def on_progress(completed: int, total: int):
                await sse_manager.publish(simulation_id, "society_activation_progress", {
                    "completed": completed,
                    "total": total,
                    "percent": round(completed / total * 100, 1),
                })

            activation_result = await run_activation(
                selected_agents, theme, on_progress=on_progress,
            )

            total_usage["prompt_tokens"] += activation_result["usage"].get("prompt_tokens", 0)
            total_usage["completion_tokens"] += activation_result["usage"].get("completion_tokens", 0)
            total_usage["total_tokens"] += activation_result["usage"].get("total_tokens", 0)

            # 活性化結果保存（個別回答を含む）
            individual_responses = []
            for agent, resp in zip(selected_agents, activation_result["responses"]):
                individual_responses.append({
                    "agent_id": agent["id"],
                    "agent_index": agent.get("agent_index", 0),
                    "stance": resp["stance"],
                    "confidence": resp["confidence"],
                    "reason": (resp.get("reason") or "")[:300],
                    "concern": (resp.get("concern") or "")[:300],
                    "priority": resp.get("priority", ""),
                })

            activation_record = SocietyResult(
                id=str(uuid.uuid4()),
                simulation_id=simulation_id,
                population_id=pop_id,
                layer="activation",
                phase_data={
                    "aggregation": activation_result["aggregation"],
                    "representative_count": len(activation_result["representatives"]),
                    "responses_summary": {
                        "total": len(activation_result["responses"]),
                        "stance_distribution": activation_result["aggregation"]["stance_distribution"],
                    },
                    "responses": individual_responses,
                },
                usage=activation_result["usage"],
            )
            session.add(activation_record)
            await session.commit()

            selected_agent_ids = [a["id"] for a in selected_agents]
            await sse_manager.publish(simulation_id, "society_activation_completed", {
                "aggregation": activation_result["aggregation"],
                "representative_count": len(activation_result["representatives"]),
                "selected_agent_ids": selected_agent_ids,
                "usage": activation_result["usage"],
            })

            # === Phase 4: Evaluation ===
            eval_metrics = await evaluate_society_simulation(
                selected_agents, activation_result["responses"],
            )

            for metric in eval_metrics:
                eval_record = EvaluationResult(
                    id=str(uuid.uuid4()),
                    simulation_id=simulation_id,
                    metric_name=metric["metric_name"],
                    score=metric["score"],
                    details=metric["details"],
                    baseline_type=metric.get("baseline_type"),
                    baseline_score=metric.get("baseline_score"),
                )
                session.add(eval_record)

            # 評価結果保存
            eval_data = {m["metric_name"]: m["score"] for m in eval_metrics}
            eval_record_society = SocietyResult(
                id=str(uuid.uuid4()),
                simulation_id=simulation_id,
                population_id=pop_id,
                layer="evaluation",
                phase_data={"metrics": eval_data},
                usage={},
            )
            session.add(eval_record_society)

            await sse_manager.publish(simulation_id, "society_evaluation_completed", {
                "metrics": eval_data,
            })

            # === Phase 4.5: Demographic Analysis ===
            demographic_analysis = analyze_demographics(
                selected_agents, activation_result["responses"],
            )
            demo_record = SocietyResult(
                id=str(uuid.uuid4()),
                simulation_id=simulation_id,
                population_id=pop_id,
                layer="demographic_analysis",
                phase_data=demographic_analysis,
                usage={},
            )
            session.add(demo_record)

            # === Phase 5: Meeting Layer ===
            meeting_participants = select_representatives(
                selected_agents,
                activation_result["responses"],
                max_citizen_reps=6,
                max_experts=4,
            )

            meeting_result = await run_meeting(
                meeting_participants, theme,
                simulation_id=simulation_id,
                num_rounds=3,
            )

            total_usage["prompt_tokens"] += meeting_result["usage"].get("prompt_tokens", 0)
            total_usage["completion_tokens"] += meeting_result["usage"].get("completion_tokens", 0)
            total_usage["total_tokens"] += meeting_result["usage"].get("total_tokens", 0)

            # Meeting レポート生成
            meeting_report = generate_meeting_report(meeting_result)

            # Meeting 結果保存（ラウンド会話・参加者を含む）
            # 会話データから usage を除外してサイズ削減
            clean_rounds = []
            for round_args in meeting_result.get("rounds", []):
                clean_round = []
                for arg in round_args:
                    clean_arg = {k: v for k, v in arg.items() if k != "usage"}
                    clean_round.append(clean_arg)
                clean_rounds.append(clean_round)

            # 参加者情報を enriched で保存
            enriched_participants = []
            for p in meeting_participants:
                info = {
                    "role": p["role"],
                    "expertise": p.get("expertise", ""),
                    "display_name": p.get("display_name", ""),
                }
                if p["role"] == "citizen_representative":
                    agent_profile = p.get("agent_profile", {})
                    demo = agent_profile.get("demographics", {})
                    info["agent_id"] = agent_profile.get("id", "")
                    info["agent_index"] = agent_profile.get("agent_index", 0)
                    info["occupation"] = demo.get("occupation", "")
                    info["region"] = demo.get("region", "")
                    info["age"] = demo.get("age", 0)
                    info["stance"] = p.get("stance", "")
                enriched_participants.append(info)

            meeting_record = SocietyResult(
                id=str(uuid.uuid4()),
                simulation_id=simulation_id,
                population_id=pop_id,
                layer="meeting",
                phase_data={
                    "report": meeting_report,
                    "participant_count": len(meeting_participants),
                    "rounds": clean_rounds,
                    "participants": enriched_participants,
                    "synthesis": meeting_result.get("synthesis", {}),
                },
                usage=meeting_result["usage"],
            )
            session.add(meeting_record)
            await session.commit()

            # === Phase 5.5: Narrative Report ===
            narrative = generate_narrative(
                selected_agents,
                activation_result["responses"],
                meeting_result.get("synthesis", {}),
                activation_result["aggregation"],
                demographic_analysis,
                meeting_rounds=meeting_result.get("rounds"),
            )
            narrative_record = SocietyResult(
                id=str(uuid.uuid4()),
                simulation_id=simulation_id,
                population_id=pop_id,
                layer="narrative",
                phase_data=narrative,
                usage={},
            )
            session.add(narrative_record)

            # === Phase 6: Persistent Society (記憶圧縮 + グラフ進化) ===
            await update_agent_memories(
                session, selected_agents, activation_result["responses"],
                meeting_result=meeting_result,
            )

            await evolve_social_graph(
                session, pop_id, meeting_result, meeting_participants,
            )

            # ソーシャルグラフ準備完了を通知
            edge_count_result = await session.execute(
                select(func.count()).select_from(SocialEdge).where(SocialEdge.population_id == pop_id)
            )
            edge_count = edge_count_result.scalar() or 0
            await sse_manager.publish(simulation_id, "society_social_graph_ready", {
                "population_id": pop_id,
                "edge_count": edge_count,
                "node_count": len(selected_agents),
            })

            # === 完了 ===
            sim.status = "completed"
            sim.completed_at = datetime.now(timezone.utc)
            sim.metadata_json = {
                **dict(sim.metadata_json or {}),
                "society_result": {
                    "population_id": pop_id,
                    "population_count": len(agents),
                    "selected_count": len(selected_agents),
                    "aggregation": activation_result["aggregation"],
                    "evaluation": eval_data,
                    "meeting": meeting_report,
                    "usage": total_usage,
                },
            }
            await session.commit()

            await sse_manager.publish(simulation_id, "society_completed", {
                "simulation_id": simulation_id,
                "aggregation": activation_result["aggregation"],
                "evaluation": eval_data,
                "meeting_available": True,
                "usage": total_usage,
            })

            logger.info("Society simulation %s completed", simulation_id)

        except Exception as e:
            logger.error("Society simulation %s failed: %s", simulation_id, e, exc_info=True)
            await session.rollback()
            sim.status = "failed"
            sim.error_message = f"{type(e).__name__}: {e}"[:500]
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })
