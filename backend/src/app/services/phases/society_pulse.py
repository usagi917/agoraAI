"""Society Pulse フェーズ: Population→選抜→活性化→評価→代表者選出"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from src.app.config import settings
from src.app.models.conversation_log import ConversationLog
from src.app.models.evaluation_result import EvaluationResult
from src.app.models.simulation import Simulation
from src.app.models.society_result import SocietyResult
from src.app.services.conversation_log_store import persist_conversation_logs
from src.app.services.society.activation_layer import run_activation
from src.app.services.society.agent_selector import select_agents
from src.app.services.society.demographic_analyzer import analyze_demographics
from src.app.services.society.evaluation import evaluate_society_simulation
from src.app.services.society.kg_enricher import enrich_agents_from_kg
from src.app.services.society.kg_evolution_service import KGEvolutionService
from src.app.services.society.persona_generator import (
    generate_persona_narratives_post_activation,
)
from src.app.services.society.population_generator import get_default_population_size
from src.app.services.society.population_propagation import run_population_propagation
from src.app.services.society.representative_selector import select_representatives
from src.app.services.society.society_orchestrator import (
    _diagnostic_config,
    _estimate_theme_category,
    _get_or_create_population,
    _load_population_edges,
    _maybe_inject_anchor_prior,
    _phase_theme_anchor,
    _save_network,
)
from src.app.services.society.survey_anchor import resolve_and_apply_anchor
from src.app.services.society.validation_pipeline import (
    auto_compare,
    build_distribution_prediction_payload,
    register_prediction_evaluation,
    register_result,
)
from src.app.services.validation_summary import build_validation_summary
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


def _phase_limits(cognitive_config: dict | None = None) -> dict[str, int]:
    """選抜数・活性化同時実行数を cognitive config (game_master) から導出する。

    値が欠損・不正な場合は従来のハードコード値にフォールバックする。
    """
    defaults = {"target_count": 100, "max_concurrency": 30}
    try:
        config = cognitive_config if cognitive_config is not None else settings.load_cognitive_config()
        gm = config.get("game_master") or {}
    except Exception:
        logger.warning("Failed to load cognitive config; using default phase limits")
        return defaults

    limits = dict(defaults)
    for key, cfg_key in (("target_count", "max_active_agents"), ("max_concurrency", "max_concurrent_agents")):
        value = gm.get(cfg_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and int(value) > 0:
            limits[key] = int(value)
    return limits


def _propagation_config(cognitive_config: dict | None = None) -> dict:
    """全人口意見伝播の設定を cognitive config (opinion_propagation) から導出する。

    値が欠損・不正な場合はデフォルトにフォールバックする。
    """
    defaults: dict = {"enabled": True, "max_timesteps": 8, "confidence_threshold": 0.5}
    try:
        config = cognitive_config if cognitive_config is not None else settings.load_cognitive_config()
        section = config.get("opinion_propagation") or {}
    except Exception:
        logger.warning("Failed to load cognitive config; using default propagation config")
        return defaults

    result = dict(defaults)
    enabled = section.get("enabled")
    if isinstance(enabled, bool):
        result["enabled"] = enabled
    timesteps = section.get("max_timesteps")
    if isinstance(timesteps, (int, float)) and not isinstance(timesteps, bool) and int(timesteps) > 0:
        result["max_timesteps"] = int(timesteps)
    threshold = section.get("confidence_threshold")
    if isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and 0 < float(threshold) <= 1:
        result["confidence_threshold"] = float(threshold)
    return result


@dataclass
class SocietyPulseResult:
    agents: list[dict]
    responses: list[dict]
    aggregation: dict
    evaluation: dict
    representatives: list[dict]
    usage: dict
    population_count: int = 0
    validation_summary: dict | None = None


async def _run_population_propagation_phase(
    *,
    simulation_id: str,
    pop_id: str,
    agents: list[dict],
    selected_agents: list[dict],
    individual_responses: list[dict],
    all_edges: list[dict],
    aggregation: dict,
    session: Any,
    seed: int | None,
    propagation_cfg: dict,
) -> None:
    """全人口意見伝播フェーズ。失敗しても本流を止めない（警告ログのみ）。

    activation 完了後、未活性化の大衆へ意見を伝播させ、ラウンドごとに SSE 配信し、
    結果を population_propagation レイヤーとして永続化する。aggregation には
    population_stance_distribution を in-place で追記する。

    伝播が無効、または未活性化の大衆が居ない（全員選抜済み）場合は何もしない。
    """
    if not (propagation_cfg["enabled"] and len(agents) > len(selected_agents)):
        return
    try:
        await sse_manager.publish(simulation_id, "population_propagation_started", {
            "population_count": len(agents),
            "edge_count": len(all_edges),
            "max_timesteps": propagation_cfg["max_timesteps"],
        })

        async def on_propagation_round(delta):
            await sse_manager.publish(simulation_id, "population_propagation_round", {
                "round": delta.round,
                "changes": [
                    {"i": c["agent_index"], "s": c["stance"]}
                    for c in delta.changes
                ],
                "changed_count": delta.changed_count,
                "distribution": delta.distribution,
            })

        propagation_result = await run_population_propagation(
            agents,
            individual_responses,
            all_edges,
            seed=seed,
            max_timesteps=propagation_cfg["max_timesteps"],
            confidence_threshold=propagation_cfg["confidence_threshold"],
            on_round=on_propagation_round,
        )

        session.add(SocietyResult(
            id=str(uuid.uuid4()),
            simulation_id=simulation_id,
            population_id=pop_id,
            layer="population_propagation",
            phase_data={
                "population_count": len(agents),
                "distribution": propagation_result.distribution,
                "total_rounds": propagation_result.total_rounds,
                "converged": propagation_result.converged,
                "changed_per_round": [d.changed_count for d in propagation_result.rounds],
            },
            usage={},
        ))
        await session.commit()

        aggregation["population_stance_distribution"] = propagation_result.distribution

        await sse_manager.publish(simulation_id, "population_propagation_completed", {
            "distribution": propagation_result.distribution,
            "converged": propagation_result.converged,
            "total_rounds": propagation_result.total_rounds,
            "changed_total": sum(d.changed_count for d in propagation_result.rounds),
        })
    except Exception as e:
        try:
            await session.rollback()
        except Exception as rollback_error:
            logger.warning("Population propagation rollback failed: %s", rollback_error)
        logger.warning("Population propagation failed, continuing: %s", e)


async def run_society_pulse(
    session: Any,
    sim: Simulation,
    theme: str,
    kg_entities: list[dict] | None = None,
    kg_relations: list[dict] | None = None,
) -> SocietyPulseResult:
    """Society Pulse フェーズを実行する。

    Population生成→選抜→活性化→評価→代表者選出を行い、結果を返す。
    session は呼び出し元が管理する（自分で開かない）。
    """
    simulation_id = sim.id
    diagnostic_cfg = _diagnostic_config(sim)
    total_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # === Population ===
    pop_count = get_default_population_size()
    await sse_manager.publish(simulation_id, "population_status", {
        "status": "generating",
        "target_count": pop_count,
    })

    pop_id, agents = await _get_or_create_population(
        session, sim.population_id, pop_count,
        seed=sim.seed,
        strict=bool(getattr(sim, "scenario_pair_id", None)),
    )
    sim.population_id = pop_id
    await session.commit()

    await sse_manager.publish(simulation_id, "population_status", {
        "status": "ready",
        "agent_count": len(agents),
        "population_id": pop_id,
    })

    await _save_network(session, agents, pop_id, seed=sim.seed)

    # === Selection (network centrality-aware) ===
    limits = _phase_limits()
    all_edges = await _load_population_edges(session, pop_id)
    selected_agents = await select_agents(
        agents, theme,
        target_count=limits["target_count"],
        edges=all_edges,
        seed=sim.seed,
    )

    await sse_manager.publish(simulation_id, "society_selection_completed", {
        "selected_count": len(selected_agents),
        "total_population": len(agents),
        "selected_agents": [
            {
                "id": a.get("id", ""),
                "agent_index": a.get("agent_index", i),
                "name": f"Agent-{a.get('agent_index', i)}",
                "occupation": a.get("demographics", {}).get("occupation", ""),
                "age": a.get("demographics", {}).get("age", 0),
                "region": a.get("demographics", {}).get("region", ""),
            }
            for i, a in enumerate(selected_agents)
        ],
    })

    # === KG Enrichment (Optional) ===
    if kg_entities:
        enrich_agents_from_kg(
            selected_agents,
            kg_entities,
            kg_relations or [],
            theme,
        )
        logger.info("KG enrichment applied to %d selected agents", len(selected_agents))

    survey_data_dir = settings.config_dir / "grounding" / "survey_data"
    theme_estimate = _estimate_theme_category(theme, [])
    anchor_distribution: dict[str, float] | None = None
    anchor_source = "none"
    anchor_survey_ids: list[str] = []
    if diagnostic_cfg:
        (
            survey_data_dir,
            theme_estimate,
            anchor_distribution,
            anchor_source,
            anchor_survey_ids,
        ) = _phase_theme_anchor(theme, [], simulation_id, diagnostic_cfg=diagnostic_cfg)
        _maybe_inject_anchor_prior(
            selected_agents,
            anchor_distribution,
            diagnostic_cfg,
            sim.seed,
        )

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
        selected_agents, theme,
        max_concurrency=limits["max_concurrency"],
        on_progress=on_progress,
    )

    if diagnostic_cfg:
        anchor_application = resolve_and_apply_anchor(
            activation_result["aggregation"].get("stance_distribution", {}),
            theme,
            theme_estimate.category,
            diagnostic_cfg=diagnostic_cfg,
            survey_data_dir=survey_data_dir,
            anchor_distribution=anchor_distribution,
            anchor_source=anchor_source,
            anchor_survey_ids=anchor_survey_ids,
        )
        if anchor_application.anchor_distribution is not None:
            activation_result["aggregation"]["anchor_distribution"] = (
                anchor_application.anchor_distribution
            )
            activation_result["aggregation"]["anchor_source"] = anchor_application.source
            activation_result["aggregation"]["anchor_survey_ids"] = (
                anchor_application.source_survey_ids
            )
        if anchor_application.applied:
            activation_result["aggregation"]["stance_distribution_pre_anchor"] = (
                anchor_application.pre_distribution
            )
            activation_result["aggregation"]["stance_distribution"] = (
                anchor_application.post_distribution
            )

    for key in total_usage:
        total_usage[key] += activation_result["usage"].get(key, 0)

    # 個別回答を保存
    individual_responses = []
    activation_logs: list[ConversationLog] = []
    for agent, resp in zip(selected_agents, activation_result["responses"]):
        individual_responses.append({
            "agent_id": agent["id"],
            "agent_index": agent.get("agent_index", 0),
            "stance": resp["stance"],
            "confidence": resp["confidence"],
            "reason": resp.get("reason") or "",
            "personal_story": resp.get("personal_story") or "",
            "concern": resp.get("concern") or "",
            "priority": resp.get("priority", ""),
        })

        # ConversationLog に activation 発言を保存
        demo = agent.get("demographics", {})
        agent_name = f"{demo.get('occupation', '不明')}・{demo.get('age', '?')}歳・{demo.get('region', '不明')}"
        reason = resp.get("reason") or ""
        personal_story = resp.get("personal_story") or ""
        concern = resp.get("concern") or ""
        content_parts = []
        if resp.get("stance"):
            content_parts.append(f"【スタンス】{resp['stance']}（信頼度: {resp.get('confidence', 0):.0%}）")
        if reason:
            content_parts.append(f"【理由】{reason}")
        if personal_story:
            content_parts.append(f"【体験談】{personal_story}")
        if concern:
            content_parts.append(f"【懸念】{concern}")

        if content_parts and not resp.get("_failed"):
            activation_logs.append(ConversationLog(
                simulation_id=simulation_id,
                phase="activation",
                round_number=0,
                participant_name=agent_name,
                participant_role="citizen",
                participant_index=agent.get("agent_index", 0),
                content_text="\n".join(content_parts),
                content_json=resp,
                stance=resp.get("stance", ""),
            ))

    await persist_conversation_logs(
        session,
        activation_logs,
        context="activation conversation logs",
    )

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

    # === Population Propagation: 全人口への意見伝播 ===
    await _run_population_propagation_phase(
        simulation_id=simulation_id,
        pop_id=pop_id,
        agents=agents,
        selected_agents=selected_agents,
        individual_responses=individual_responses,
        all_edges=all_edges,
        aggregation=activation_result["aggregation"],
        session=session,
        seed=sim.seed,
        propagation_cfg=_propagation_config(),
    )

    # === Post-Activation Persona Narrative Generation ===
    await sse_manager.publish(simulation_id, "persona_generation_started", {
        "agent_count": len(selected_agents),
    })
    try:
        selected_agents = await generate_persona_narratives_post_activation(
            selected_agents, activation_result["responses"], theme,
        )
        generated = sum(1 for a in selected_agents if a.get("persona_narrative"))
        logger.info("Post-activation persona narratives: %d/%d generated", generated, len(selected_agents))
    except Exception as e:
        logger.warning("Post-activation persona generation failed, continuing without: %s", e)

    # === KG Evolution: activation回答からKGを抽出しSSE配信 ===
    try:
        kg_evo = KGEvolutionService()
        if kg_entities:
            kg_evo.seed_from_existing(kg_entities, kg_relations or [])
        await kg_evo.extract_and_publish_from_activation(
            simulation_id,
            individual_responses,
            theme,
        )
    except Exception as e:
        logger.warning("KG evolution from activation failed: %s", e)

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

    # === Validation Summary ===
    validation_summary = build_validation_summary(
        theme=theme,
        theme_category=theme_estimate.category,
        distribution=activation_result["aggregation"].get("stance_distribution", {}),
    )
    if validation_summary.get("corrected_distribution"):
        activation_result["aggregation"]["calibrated_stance_distribution"] = validation_summary[
            "corrected_distribution"
        ]
        activation_result["aggregation"]["calibration_status"] = validation_summary[
            "calibration_status"
        ]
    sim.metadata_json = {
        **dict(sim.metadata_json or {}),
        "validation_summary": validation_summary,
    }
    await session.commit()

    if validation_summary.get("survey_anchor_status") == "実調査アンカーあり":
        await sse_manager.publish(simulation_id, "validation_comparison_completed", {
            "distribution_error": validation_summary.get("distribution_error"),
            "best_match_source": validation_summary.get("best_match_source"),
            "matched_survey_count": validation_summary.get("matched_survey_count"),
        })

    try:
        validation_record = await register_result(
            session,
            simulation_id=simulation_id,
            theme=theme,
            theme_category=theme_estimate.category,
            distribution=activation_result["aggregation"].get("stance_distribution", {}),
            calibrated_distribution=validation_summary.get("corrected_distribution"),
            theme_category_estimate=theme_estimate,
        )
        comparison = await auto_compare(
            session,
            validation_record,
            str(settings.config_dir / "grounding" / "survey_data"),
        )
        actual_payload = None
        if comparison:
            best_survey = next(
                (
                    survey
                    for survey in comparison.get("matched_surveys", [])
                    if survey.get("source") == comparison.get("best_match_source")
                ),
                None,
            )
            if best_survey:
                actual_payload = {"actual_distribution": best_survey["stance_distribution"]}
        await register_prediction_evaluation(
            session,
            simulation_id=simulation_id,
            prediction_type="distribution",
            theme_category=theme_estimate.category,
            source="society_pulse",
            predicted_payload=build_distribution_prediction_payload(activation_result["aggregation"]),
            actual_payload=actual_payload,
        )
    except Exception as exc:
        await session.rollback()
        logger.warning("Validation record persistence failed, continuing: %s", exc)

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
    representatives = await select_representatives(
        selected_agents,
        activation_result["responses"],
        max_citizen_reps=6,
        max_experts=4,
        theme=theme,
    )

    return SocietyPulseResult(
        agents=selected_agents,
        responses=activation_result["responses"],
        aggregation=activation_result["aggregation"],
        evaluation=eval_data,
        representatives=representatives,
        usage=total_usage,
        population_count=len(agents),
        validation_summary=validation_summary,
    )
