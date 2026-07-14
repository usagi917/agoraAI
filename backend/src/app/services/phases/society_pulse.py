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
from src.app.services.graph_activity import (
    GraphActivityCreate,
    persist_graph_activity_events,
    propagation_changes_to_graph_events,
)
from src.app.services.society.accuracy_config import is_enabled
from src.app.services.society.activation_layer import run_activation
from src.app.services.society.activation_store import persist_activation_chunk
from src.app.services.society.agent_selector import select_agents
from src.app.services.society.demographic_analyzer import analyze_demographics
from src.app.services.society.diagnostic_baseline import run_single_llm_distribution
from src.app.services.society.ensemble import (
    blend_distributions,
    get_ensemble_beta,
    is_uniform_fallback,
)
from src.app.services.society.evaluation import evaluate_society_simulation
from src.app.services.society.hybrid_calibration import apply_distribution_residual
from src.app.services.society.hybrid_config import (
    HybridInferenceConfig,
    load_hybrid_inference_config,
)
from src.app.services.society.hybrid_orchestrator import (
    run_hybrid_activation,
    run_hybrid_social_requery,
)
from src.app.services.society.kg_enricher import enrich_agents_from_kg
from src.app.services.society.kg_evolution_service import KGEvolutionService
from src.app.services.society.persona_generator import (
    generate_persona_narratives_post_activation,
)
from src.app.services.society.population_generator import get_default_population_size
from src.app.services.society.population_propagation import (
    PopulationPropagationResult,
    run_population_propagation,
)
from src.app.services.society.population_voice import generate_population_voices
from src.app.services.society.representative_selector import select_representatives
from src.app.services.society.society_orchestrator import (
    _diagnostic_config,
    _estimate_theme_category,
    _get_or_create_population,
    _load_population_edges,
    _load_selected_social_edges,
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

MAX_VISUALIZED_ACTIVATION_NODES = 200
MAX_ACTIVATION_CONVERSATION_LOGS = 100
MAX_KG_ACTIVATION_RESPONSES = 100
MAX_PROPAGATION_GRAPH_CHANGES_PER_ROUND = 500


def _visualized_agents(agents: list[dict], *, limit: int = MAX_VISUALIZED_ACTIVATION_NODES) -> list[dict]:
    """SSE/UI に送る住民だけを制限する。活性化対象そのものは変更しない。"""
    return agents[: max(0, limit)]


def _select_narrative_pairs(
    agents: list[dict],
    responses: list[dict],
    *,
    limit: int,
) -> list[tuple[dict, dict]]:
    """スタンスを偏らせず、ナラティブ生成対象を決定論的に選ぶ。"""
    groups: dict[str, list[tuple[dict, dict]]] = {}
    for agent, response in zip(agents, responses, strict=True):
        if response.get("_failed"):
            continue
        stance = str(response.get("stance") or "中立")
        groups.setdefault(stance, []).append((agent, response))

    for pairs in groups.values():
        pairs.sort(
            key=lambda pair: (
                -float(pair[1].get("confidence", 0.0) or 0.0),
                int(pair[0].get("agent_index", 0) or 0),
            )
        )

    selected: list[tuple[dict, dict]] = []
    stance_order = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]
    ordered_groups = [groups[stance] for stance in stance_order if stance in groups]
    ordered_groups.extend(
        groups[stance] for stance in sorted(set(groups) - set(stance_order))
    )
    while ordered_groups and len(selected) < max(0, limit):
        remaining: list[list[tuple[dict, dict]]] = []
        for group in ordered_groups:
            if group and len(selected) < limit:
                selected.append(group.pop(0))
            if group:
                remaining.append(group)
        ordered_groups = remaining
    return selected


def _calibrate_social_distribution(
    raw_distribution: dict[str, float],
    aggregation: dict,
) -> dict[str, float]:
    """Keep the learned Liquid/GPT residual after numeric social dynamics."""
    aggregation["stance_distribution_social_liquid"] = dict(raw_distribution)
    calibration = aggregation.get("hybrid_calibration") or {}
    residual = calibration.get("residual")
    if not calibration.get("applied") or not isinstance(residual, dict):
        return raw_distribution
    aggregation["stance_distribution_social_hybrid_full"] = apply_distribution_residual(
        raw_distribution,
        residual,
        shrinkage=1.0,
    )
    return apply_distribution_residual(
        raw_distribution,
        residual,
        shrinkage=float(calibration.get("shrinkage", 1.0) or 0.0),
    )


def _updated_activation_phase_data(
    phase_data: dict,
    aggregation: dict,
) -> dict:
    """Refresh the durable audit snapshot after social dynamics completes."""
    responses_summary = dict(phase_data.get("responses_summary") or {})
    responses_summary["stance_distribution"] = dict(
        aggregation.get("stance_distribution") or {}
    )
    return {
        **phase_data,
        "aggregation": dict(aggregation),
        "responses_summary": responses_summary,
    }


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


def _activation_limits(
    hybrid_config: HybridInferenceConfig,
    *,
    diagnostic: bool,
    cognitive_config: dict | None = None,
) -> dict[str, int]:
    """Use 10k limits only for the local hybrid path; keep paid legacy paths bounded."""
    if hybrid_config.enabled and not diagnostic:
        role = hybrid_config.population_activation
        return {
            "target_count": role.target_count,
            "max_concurrency": role.max_concurrency,
        }
    return _phase_limits(cognitive_config)


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
) -> PopulationPropagationResult | None:
    """全人口意見伝播フェーズ。失敗しても本流を止めない（警告ログのみ）。

    activation 完了後、全住民の意見を数値的に更新し、ラウンドごとに SSE 配信し、
    結果を population_propagation レイヤーとして永続化する。aggregation には
    population_stance_distribution を in-place で追記する。

    全員が LLM 活性化済みでも社会的相互作用は実行する。無効設定の場合のみ省略する。
    """
    if not propagation_cfg["enabled"]:
        return None
    agents_by_id = {a["id"]: a for a in agents}
    selected_ids = {a.get("id", "") for a in selected_agents}
    prev_round_stances: dict[str, str] = {}
    try:
        await sse_manager.publish(simulation_id, "population_propagation_started", {
            "population_count": len(agents),
            "edge_count": len(all_edges),
            "max_timesteps": propagation_cfg["max_timesteps"],
        })

        async def on_propagation_round(delta):
            graph_events = propagation_changes_to_graph_events(
                delta.changes[:MAX_PROPAGATION_GRAPH_CHANGES_PER_ROUND],
                phase="population_propagation",
                round=delta.round,
                stance_source_key="agent_id",
            )
            await persist_graph_activity_events(
                session,
                simulation_id,
                graph_events,
            )
            await sse_manager.publish(simulation_id, "population_propagation_round", {
                "round": delta.round,
                "changes": [
                    {"i": c["agent_index"], "s": c["stance"]}
                    for c in delta.changes[:MAX_PROPAGATION_GRAPH_CHANGES_PER_ROUND]
                ],
                "changed_count": delta.changed_count,
                "changes_truncated": (
                    len(delta.changes) > MAX_PROPAGATION_GRAPH_CHANGES_PER_ROUND
                ),
                "distribution": delta.distribution,
            })
            filtered_changes = [
                change for change in delta.changes
                if change["agent_id"] not in selected_ids
            ]
            try:
                voices = generate_population_voices(
                    filtered_changes,
                    agents_by_id,
                    round_index=delta.round,
                    prev_stances=prev_round_stances,
                    max_voices=12,
                    seed=seed,
                )
                if voices:
                    await sse_manager.publish(simulation_id, "population_voice", {
                        "round": delta.round,
                        "voices": voices,
                    })
            except Exception as e:
                logger.warning("Population voice generation failed, continuing: %s", e)
            finally:
                prev_round_stances.update({
                    change["agent_id"]: change["stance"]
                    for change in delta.changes
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
        return propagation_result
    except Exception as e:
        try:
            await session.rollback()
        except Exception as rollback_error:
            logger.warning("Population propagation rollback failed: %s", rollback_error)
        logger.warning("Population propagation failed, continuing: %s", e)
        return None


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
    hybrid_config = load_hybrid_inference_config()
    hybrid_active = hybrid_config.enabled and not diagnostic_cfg
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
    limits = _activation_limits(
        hybrid_config,
        diagnostic=bool(diagnostic_cfg),
    )
    all_edges = await _load_population_edges(session, pop_id)
    selected_agents = await select_agents(
        agents, theme,
        target_count=limits["target_count"],
        max_count=(
            limits["target_count"]
            if hybrid_active
            else 200
        ),
        edges=all_edges,
        seed=sim.seed,
    )
    visualized_agents = _visualized_agents(selected_agents)

    await sse_manager.publish(simulation_id, "society_selection_completed", {
        "selected_count": len(selected_agents),
        "activated_target_count": len(selected_agents),
        "visualized_count": len(visualized_agents),
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
            for i, a in enumerate(visualized_agents)
        ],
    })

    # === Social graph structure (early) ===
    # 意見（stance）はまだ無いが、選抜エージェント同士のソーシャル構造は
    # デモグラから既に確定済み。ライブ実行の開始直後から本物の関係性の輪を描けるよう、
    # 選抜完了の直後にエッジ構造だけを送出する（stance は活性化後に別途着色）。
    visualized_ids = {a.get("id", "") for a in visualized_agents}
    visualized_ids.discard("")
    social_edges = await _load_selected_social_edges(session, pop_id, visualized_ids)
    await sse_manager.publish(simulation_id, "society_social_graph_structure", {
        "population_id": pop_id,
        "edge_count": len(social_edges),
        "edges": social_edges,
    })
    await persist_graph_activity_events(
        session,
        simulation_id,
        [
            GraphActivityCreate(
                phase="selection",
                kind="phase_changed",
                payload={"phase": "selection"},
            ),
            *[
                GraphActivityCreate(
                    phase="selection",
                    kind="node_status",
                    source_id=agent.get("id"),
                    payload={
                        "status": "selected",
                        "agent_index": agent.get("agent_index", index),
                    },
                )
                for index, agent in enumerate(visualized_agents)
                if agent.get("id")
            ],
        ],
    )

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
    await persist_graph_activity_events(
        session,
        simulation_id,
        [GraphActivityCreate(
            phase="activation",
            kind="phase_changed",
            payload={"phase": "activation"},
        )],
    )

    async def on_progress(completed: int, total: int):
        await sse_manager.publish(simulation_id, "society_activation_progress", {
            "completed": completed,
            "total": total,
            "percent": round(completed / total * 100, 1),
        })

    if hybrid_active:
        activation_result = await run_hybrid_activation(
            session,
            simulation_id=simulation_id,
            population_id=pop_id,
            agents=selected_agents,
            theme=theme,
            seed=sim.seed,
            config=hybrid_config,
            on_progress=on_progress,
            theme_category=theme_estimate.category,
        )
    else:
        activation_result = await run_activation(
            selected_agents,
            theme,
            max_concurrency=limits["max_concurrency"],
            on_progress=on_progress,
        )

    if not hybrid_active and not diagnostic_cfg and is_enabled("single_llm_ensemble"):
        aggregation = activation_result["aggregation"]
        try:
            single_distribution, single_usage = await run_single_llm_distribution(theme, sim.seed)
        except Exception as exc:
            logger.warning("Single-LLM ensemble skipped after baseline error: %s", exc)
            aggregation["ensemble_skipped"] = "error"
        else:
            for key in total_usage:
                total_usage[key] += single_usage.get(key, 0)
            aggregation["single_llm_distribution"] = single_distribution
            if is_uniform_fallback(single_distribution):
                aggregation["ensemble_skipped"] = "uniform_fallback"
            else:
                swarm_distribution = aggregation["stance_distribution"]
                beta = get_ensemble_beta()
                aggregation["stance_distribution_pre_ensemble"] = swarm_distribution.copy()
                aggregation["ensemble_beta"] = beta
                aggregation["stance_distribution"] = blend_distributions(
                    swarm_distribution,
                    single_distribution,
                    beta,
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
    for agent, resp in zip(selected_agents, activation_result["responses"], strict=True):
        resp.setdefault("agent_id", agent["id"])
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

        if (
            content_parts
            and not resp.get("_failed")
            and len(activation_logs) < MAX_ACTIVATION_CONVERSATION_LOGS
        ):
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

    activation_phase_data = {
        "aggregation": activation_result["aggregation"],
        "representative_count": len(activation_result["representatives"]),
        "responses_summary": {
            "total": len(activation_result["responses"]),
            "stance_distribution": activation_result["aggregation"]["stance_distribution"],
        },
    }
    if hybrid_active:
        activation_phase_data.update({
            "responses_persisted_separately": True,
            "response_sample": individual_responses[:MAX_ACTIVATION_CONVERSATION_LOGS],
        })
    else:
        activation_phase_data["responses"] = individual_responses

    activation_record = SocietyResult(
        id=str(uuid.uuid4()),
        simulation_id=simulation_id,
        population_id=pop_id,
        layer="activation",
        phase_data=activation_phase_data,
        usage=activation_result["usage"],
    )
    session.add(activation_record)
    await session.commit()

    visualized_agent_ids = [a["id"] for a in visualized_agents]
    await sse_manager.publish(simulation_id, "society_activation_completed", {
        "aggregation": activation_result["aggregation"],
        "representative_count": len(activation_result["representatives"]),
        "activated_count": activation_result["aggregation"].get(
            "activated_count", len(individual_responses)
        ),
        "gpt_validated_count": activation_result["aggregation"].get("gpt_validated_count", 0),
        "selected_agent_ids": visualized_agent_ids,
        "visualized_count": len(visualized_agent_ids),
        "usage": activation_result["usage"],
    })
    await persist_graph_activity_events(
        session,
        simulation_id,
        [
            GraphActivityCreate(
                phase="activation",
                kind="node_status",
                source_id=response["agent_id"],
                payload={
                    "status": "activated",
                    "stance": response["stance"],
                    "confidence": response["confidence"],
                },
            )
            for response in individual_responses
            if response["agent_id"] in visualized_ids
        ],
    )

    # === Population Propagation: 全人口への意見伝播 ===
    propagation_result = await _run_population_propagation_phase(
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
    if propagation_result is not None and hybrid_active:
        final_stances = {
            str(item["agent_id"]): item["stance"]
            for item in propagation_result.final_stances
        }
        for response in activation_result["responses"]:
            initial_stance = response["stance"]
            response["initial_stance"] = initial_stance
            response["propagated_stance"] = final_stances.get(
                str(response.get("agent_id") or ""), initial_stance
            )

        social_result: dict = {
            "responses": [],
            "usage": {},
            "requeried_count": 0,
            "changed_count": 0,
        }
        try:
            social_result = await run_hybrid_social_requery(
                session,
                simulation_id=simulation_id,
                population_id=pop_id,
                agents=selected_agents,
                initial_responses=activation_result["responses"],
                final_stances=propagation_result.final_stances,
                theme=theme,
                seed=sim.seed,
                config=hybrid_config,
            )
        except Exception as exc:
            logger.warning("Liquid social requery failed, using numeric update: %s", exc)

        social_by_id = {
            str(response.get("agent_id") or ""): response
            for response in social_result.get("responses", [])
            if not response.get("_failed")
        }
        individual_by_id = {
            response["agent_id"]: response for response in individual_responses
        }
        for response in activation_result["responses"]:
            agent_id = str(response.get("agent_id") or "")
            response["stance"] = response["propagated_stance"]
            social_response = social_by_id.get(agent_id)
            if social_response:
                for field in ("stance", "confidence", "reason", "concern", "priority"):
                    if field in social_response:
                        response[field] = social_response[field]
                response["social_requeried"] = True
            stored = individual_by_id.get(agent_id)
            if stored is not None:
                stored.update({
                    "initial_stance": response["initial_stance"],
                    "propagated_stance": response["propagated_stance"],
                    "stance": response["stance"],
                    "confidence": response["confidence"],
                    "reason": response.get("reason") or "",
                    "concern": response.get("concern") or "",
                    "priority": response.get("priority") or "",
                    "social_requeried": bool(response.get("social_requeried")),
                })

        final_counts: dict[str, int] = {}
        for response in activation_result["responses"]:
            if response.get("_failed") or not response.get("stance"):
                continue
            stance = str(response["stance"])
            final_counts[stance] = final_counts.get(stance, 0) + 1
        total_final = sum(final_counts.values())
        raw_final_distribution = {
            stance: count / total_final
            for stance, count in final_counts.items()
        } if total_final else {}
        aggregation = activation_result["aggregation"]
        final_distribution = _calibrate_social_distribution(
            raw_final_distribution,
            aggregation,
        )
        aggregation["stance_distribution_pre_social"] = dict(
            aggregation.get("stance_distribution", {})
        )
        aggregation["stance_distribution"] = final_distribution
        aggregation["population_stance_distribution_after_requery"] = final_distribution
        aggregation["social_changed_count"] = social_result.get("changed_count", 0)
        aggregation["social_requeried_count"] = social_result.get("requeried_count", 0)
        activation_phase_data = _updated_activation_phase_data(
            activation_phase_data,
            aggregation,
        )
        activation_record.phase_data = activation_phase_data
        for key in total_usage:
            total_usage[key] += int(social_result.get("usage", {}).get(key, 0) or 0)

        for start in range(0, len(selected_agents), 256):
            chunk_agents = selected_agents[start : start + 256]
            chunk_responses = activation_result["responses"][start : start + 256]
            await persist_activation_chunk(
                session,
                simulation_id=simulation_id,
                population_id=pop_id,
                stage="social_final",
                run_seed=sim.seed,
                records=[
                    {
                        "agent_id": agent["id"],
                        "agent_index": agent.get("agent_index", start + offset),
                        "provider": "social_dynamics",
                        "model": "network+liquid_requery",
                        "response": response,
                        "usage": {},
                    }
                    for offset, (agent, response) in enumerate(
                        zip(chunk_agents, chunk_responses, strict=True)
                    )
                ],
            )

        session.add(SocietyResult(
            id=str(uuid.uuid4()),
            simulation_id=simulation_id,
            population_id=pop_id,
            layer="social_requery",
            phase_data={
                "changed_count": aggregation["social_changed_count"],
                "requeried_count": aggregation["social_requeried_count"],
                "distribution": final_distribution,
            },
            usage=social_result.get("usage", {}),
        ))
        await session.commit()

    # === Post-Activation Persona Narrative Generation ===
    narrative_pairs = _select_narrative_pairs(
        selected_agents,
        activation_result["responses"],
        limit=(
            hybrid_config.narrative_count
            if hybrid_active
            else len(selected_agents)
        ),
    )
    narrative_agents = [agent for agent, _ in narrative_pairs]
    narrative_responses = [response for _, response in narrative_pairs]
    await sse_manager.publish(simulation_id, "persona_generation_started", {
        "agent_count": len(narrative_agents),
        "population_activated_count": len(selected_agents),
    })
    try:
        await generate_persona_narratives_post_activation(
            narrative_agents,
            narrative_responses,
            theme,
            max_concurrency=(
                hybrid_config.population_activation.max_concurrency
                if hybrid_active
                else limits["max_concurrency"]
            ),
            provider_override=(
                hybrid_config.population_activation.provider
                if hybrid_active
                else None
            ),
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
            individual_responses[:MAX_KG_ACTIVATION_RESPONSES],
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
    activation_result["aggregation"].setdefault(
        "activated_count",
        sum(not response.get("_failed") for response in activation_result["responses"]),
    )
    activation_result["aggregation"].setdefault("gpt_validated_count", 0)
    activation_result["aggregation"]["council_representative_count"] = len(representatives)

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
