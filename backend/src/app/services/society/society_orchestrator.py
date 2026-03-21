"""Society オーケストレータ: Population→選抜→活性化→評価→結果保存"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from src.app.database import async_session
from src.app.models.population import Population
from src.app.models.agent_profile import AgentProfile
from src.app.models.social_edge import SocialEdge
from src.app.models.simulation import Simulation
from src.app.models.society_result import SocietyResult
from src.app.models.evaluation_result import EvaluationResult
from src.app.services.society.population_generator import generate_population
from src.app.services.society.network_generator import generate_network
from src.app.services.society.agent_selector import select_agents
from src.app.services.society.activation_layer import run_activation
from src.app.services.society.evaluation import evaluate_society_simulation
from src.app.services.society.representative_selector import select_representatives
from src.app.services.society.meeting_layer import run_meeting
from src.app.services.society.meeting_report import generate_meeting_report
from src.app.services.society.memory_compressor import update_agent_memories
from src.app.services.society.graph_evolution import evolve_social_graph
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def _get_or_create_population(session, population_id: str | None = None, count: int = 1000) -> tuple[str, list[dict]]:
    """既存の Population を取得するか、新規生成する。"""
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
        agent_count=count,
        generation_params={"count": count},
        status="generating",
    )
    session.add(population)
    await session.commit()

    agents = await generate_population(pop_id, count)

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

            pop_count = 1000
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

            # 活性化結果保存
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
                },
                usage=activation_result["usage"],
            )
            session.add(activation_record)
            await session.commit()

            await sse_manager.publish(simulation_id, "society_activation_completed", {
                "aggregation": activation_result["aggregation"],
                "representative_count": len(activation_result["representatives"]),
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

            # Meeting 結果保存
            meeting_record = SocietyResult(
                id=str(uuid.uuid4()),
                simulation_id=simulation_id,
                population_id=pop_id,
                layer="meeting",
                phase_data={
                    "report": meeting_report,
                    "participant_count": len(meeting_participants),
                },
                usage=meeting_result["usage"],
            )
            session.add(meeting_record)
            await session.commit()

            # === Phase 6: Persistent Society (記憶圧縮 + グラフ進化) ===
            await update_agent_memories(
                session, selected_agents, activation_result["responses"],
                meeting_result=meeting_result,
            )

            await evolve_social_graph(
                session, pop_id, meeting_result, meeting_participants,
            )

            # === 完了 ===
            sim.status = "completed"
            sim.completed_at = datetime.now(timezone.utc)
            sim.metadata_json = {
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
            sim.status = "failed"
            sim.error_message = f"{type(e).__name__}: {e}"[:500]
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })
