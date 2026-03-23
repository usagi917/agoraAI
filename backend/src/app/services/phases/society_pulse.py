"""Society Pulse フェーズ: Population→選抜→活性化→評価→代表者選出"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.app.models.simulation import Simulation
from src.app.models.society_result import SocietyResult
from src.app.models.evaluation_result import EvaluationResult
from src.app.services.society.society_orchestrator import (
    _get_or_create_population,
    _save_network,
)
from src.app.services.society.population_generator import get_default_population_size
from src.app.services.society.agent_selector import select_agents
from src.app.services.society.activation_layer import run_activation
from src.app.services.society.evaluation import evaluate_society_simulation
from src.app.services.society.representative_selector import select_representatives
from src.app.services.society.demographic_analyzer import analyze_demographics
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


@dataclass
class SocietyPulseResult:
    agents: list[dict]
    responses: list[dict]
    aggregation: dict
    evaluation: dict
    representatives: list[dict]
    usage: dict


async def run_society_pulse(
    session: Any,
    sim: Simulation,
    theme: str,
) -> SocietyPulseResult:
    """Society Pulse フェーズを実行する。

    Population生成→選抜→活性化→評価→代表者選出を行い、結果を返す。
    session は呼び出し元が管理する（自分で開かない）。
    """
    simulation_id = sim.id
    total_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # === Population ===
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

    await _save_network(session, agents, pop_id)

    # === Selection ===
    selected_agents = await select_agents(agents, theme, target_count=100)

    await sse_manager.publish(simulation_id, "society_selection_completed", {
        "selected_count": len(selected_agents),
        "total_population": len(agents),
        "selected_agents": [
            {
                "agent_index": a.get("agent_index", i),
                "name": f"Agent-{a.get('agent_index', i)}",
                "occupation": a.get("demographics", {}).get("occupation", ""),
                "age": a.get("demographics", {}).get("age", 0),
                "region": a.get("demographics", {}).get("region", ""),
            }
            for i, a in enumerate(selected_agents)
        ],
    })

    # === Activation ===
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

    for key in total_usage:
        total_usage[key] += activation_result["usage"].get(key, 0)

    # 個別回答を保存
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

    # === Evaluation ===
    eval_metrics = await evaluate_society_simulation(
        selected_agents, activation_result["responses"],
    )
    eval_data = {m["metric_name"]: m["score"] for m in eval_metrics}

    for metric in eval_metrics:
        session.add(EvaluationResult(
            id=str(uuid.uuid4()),
            simulation_id=simulation_id,
            metric_name=metric["metric_name"],
            score=metric["score"],
            details=metric["details"],
            baseline_type=metric.get("baseline_type"),
            baseline_score=metric.get("baseline_score"),
        ))

    session.add(SocietyResult(
        id=str(uuid.uuid4()),
        simulation_id=simulation_id,
        population_id=pop_id,
        layer="evaluation",
        phase_data={"metrics": eval_data},
        usage={},
    ))
    await session.commit()

    await sse_manager.publish(simulation_id, "society_evaluation_completed", {
        "metrics": eval_data,
    })

    # === Demographic Analysis ===
    demographic_analysis = analyze_demographics(
        selected_agents, activation_result["responses"],
    )
    session.add(SocietyResult(
        id=str(uuid.uuid4()),
        simulation_id=simulation_id,
        population_id=pop_id,
        layer="demographic_analysis",
        phase_data=demographic_analysis,
        usage={},
    ))

    # === Representatives ===
    representatives = select_representatives(
        selected_agents,
        activation_result["responses"],
        max_citizen_reps=6,
        max_experts=4,
    )

    return SocietyPulseResult(
        agents=selected_agents,
        responses=activation_result["responses"],
        aggregation=activation_result["aggregation"],
        evaluation=eval_data,
        representatives=representatives,
        usage=total_usage,
    )
