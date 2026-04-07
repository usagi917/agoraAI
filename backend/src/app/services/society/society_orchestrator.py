"""Society オーケストレータ: Population→選抜→活性化→ネットワーク伝播→評価→結果保存

Swarm Intelligence Pipeline:
  Population → Network → Selection → Grounding → Activation
  → Network Propagation (Bounded Confidence + Friedkin-Johnsen)
  → Stigmergy → Prediction Market → Echo Chamber Detection
  → Representative Selection (from propagated opinions)
  → Meeting → Evaluation → Narrative → Memory/Graph Evolution
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from src.app.config import settings
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
from src.app.services.society.data_grounding import load_grounding_facts, distribute_facts_to_agents
from src.app.services.society.evaluation import evaluate_society_simulation
from src.app.services.society.representative_selector import select_representatives
from src.app.services.society.meeting_layer import run_meeting, enrich_meeting_with_clusters
from src.app.services.society.meeting_report import generate_meeting_report
from src.app.services.society.memory_compressor import update_agent_memories
from src.app.services.society.graph_evolution import evolve_social_graph
from src.app.services.society.demographic_analyzer import analyze_demographics
from src.app.services.society.narrative_generator import generate_narrative
from src.app.services.society.deliberation_quality import compute_dqi, measure_opinion_change
from src.app.services.society.provenance import build_provenance
from src.app.services.society.network_propagation import (
    run_network_propagation,
    _convert_opinion_to_stance,
)
from src.app.services.society.stigmergy_service import StigmergyBoard
from src.app.services.society.prediction_market import PredictionMarket
from src.app.services.society.statistical_inference import compute_independence_weights
from src.app.services.society.activation_layer import _aggregate_opinions
from src.app.services.society.calibration import platt_recalibrate
from src.app.services.society.emergence_tracker import EmergenceTracker
from src.app.services.society.output_validator import explain_activation_meeting_gap
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "economy": ["経済", "景気", "物価", "金利", "賃金", "雇用", "収入", "GDP", "インフレ", "デフレ", "財政", "税"],
    "politics": ["政治", "選挙", "外交", "政党", "国会", "法案", "政策", "内閣", "議会"],
    "security": ["防衛", "安全保障", "自衛隊", "軍事", "安保", "テロ", "有事"],
    "environment": ["環境", "エネルギー", "原発", "再生可能", "脱炭素", "気候", "温暖化"],
    "social": ["社会", "福祉", "教育", "医療", "介護", "少子化", "高齢", "年金", "生活"],
}


def _estimate_theme_category(theme: str, grounding_facts: list[dict] | None = None) -> str:
    """テーマ文やグラウンディングファクトからテーマカテゴリを推定する。"""
    # grounding_facts にカテゴリ情報があればそれを優先
    if grounding_facts:
        for fact in grounding_facts:
            cat = fact.get("theme_category") or fact.get("category")
            if cat and cat in _CATEGORY_KEYWORDS:
                return cat

    # テーマ文からキーワードマッチでカテゴリを推定
    best_category = "social"
    best_count = 0
    for category, keywords in _CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in theme)
        if count > best_count:
            best_count = count
            best_category = category

    return best_category


def _build_activation_phase_data(
    activation_result: dict,
    representative_count: int,
    individual_responses: list[dict],
) -> dict:
    """活性化レイヤーの永続化 payload を構築する.

    propagation 後に independence 再集計が走った場合は、
    pre/post aggregation を同じ activation レコードに保持する。
    """
    phase_data = {
        "aggregation": activation_result["aggregation"],
        "representative_count": representative_count,
        "responses_summary": {
            "total": len(activation_result["responses"]),
            "stance_distribution": activation_result["aggregation"].get(
                "stance_distribution", {}
            ),
        },
        "responses": individual_responses,
    }

    aggregation_pre = activation_result.get("aggregation_pre_independence")
    if aggregation_pre is not None:
        phase_data["aggregation_pre_independence"] = aggregation_pre
        phase_data["responses_summary_pre_independence"] = {
            "total": len(activation_result["responses"]),
            "stance_distribution": aggregation_pre.get("stance_distribution", {}),
        }

    return phase_data


def _build_independence_reaggregation_summary(activation_result: dict) -> dict:
    """pre/post independence 再集計の比較サマリを返す."""
    aggregation_post = activation_result["aggregation"]
    aggregation_pre = activation_result.get("aggregation_pre_independence")

    return {
        "applied": aggregation_pre is not None,
        "effective_sample_size_pre": (
            aggregation_pre.get("effective_sample_size")
            if aggregation_pre is not None else None
        ),
        "effective_sample_size_post": aggregation_post.get("effective_sample_size"),
        "stance_distribution_pre": (
            aggregation_pre.get("stance_distribution")
            if aggregation_pre is not None else None
        ),
        "stance_distribution_post": aggregation_post.get("stance_distribution"),
    }


def _apply_independence_re_aggregation(
    activation_result: dict,
    clusters: list[dict],
    edges: list[dict],
    agent_ids: list[str],
    agents: list[dict],
) -> dict[str, float]:
    """independence weights を計算し、activation_result を second-pass で再集計する.

    - 重みが計算でき、かつ非自明（全員 1.0 でない）な場合のみ再集計を実行。
    - 再集計した場合は activation_result["aggregation_pre_independence"] に元の集計を保存し、
      activation_result["aggregation"] を補正後に差し替える。
    - 再集計しなかった場合は activation_result を変更しない。

    Returns:
        計算された independence_weights (agent_id → weight)。空 dict の場合は計算不可。
    """
    if not clusters or not agent_ids:
        return {}

    try:
        independence_weights = compute_independence_weights(clusters, edges, agent_ids)
    except Exception as exc:
        logger.warning("Independence weight computation failed: %s", exc)
        return {}

    # 全員ほぼ 1.0 なら再集計不要
    if all(abs(w - 1.0) < 1e-6 for w in independence_weights.values()):
        return independence_weights

    # Phase A の集計を退避
    aggregation_pre = activation_result["aggregation"]

    # Phase B: independence-weighted re-aggregation (original stance を使用)
    try:
        re_aggregation = _aggregate_opinions(
            activation_result["responses"],
            agents=agents,
            independence_weights=independence_weights,
        )
        activation_result["aggregation_pre_independence"] = aggregation_pre
        activation_result["aggregation"] = re_aggregation
        logger.info(
            "Independence-weighted re-aggregation completed: n_eff=%.1f (pre=%.1f)",
            re_aggregation.get("effective_sample_size", 0),
            aggregation_pre.get("effective_sample_size", 0),
        )
    except Exception as exc:
        logger.warning("Independence-weighted re-aggregation failed: %s", exc)

    return independence_weights


def _get_prediction_market_config(mix_config: dict) -> dict:
    """予測市場のコンフィグを返す。

    Design Decision:
        デフォルトでは pre-propagation stance を使用する。
        ネットワーク伝播前のエージェント初期意見が、各エージェントの独立した判断を
        より正確に反映するため。post-propagation は社会的影響を受けた後の意見であり、
        独立性の低い（＝予測市場の情報集約効果が薄い）データとなる。

        use_post_propagation=True に切り替えると、ネットワーク伝播後の
        （社会的影響を反映した）スタンスで予測市場のベットを行う。
    """
    pm_config = mix_config.get("prediction_market", {})
    return {
        "use_post_propagation": bool(pm_config.get("use_post_propagation", False)),
    }


async def _get_or_create_population(
    session,
    population_id: str | None = None,
    count: int | None = None,
    seed: int | None = None,
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

    agents = await generate_population(pop_id, resolved_count, seed=seed)

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
                session, sim.population_id, pop_count, seed=sim.seed,
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

            # === Phase 2.7: Grounding ===
            grounding_facts = []
            try:
                grounding_facts = load_grounding_facts(theme)
                agent_facts = distribute_facts_to_agents(selected_agents, grounding_facts)
                # 各エージェントに grounding_facts を付与
                for idx, agent in enumerate(selected_agents):
                    agent["grounding_facts"] = agent_facts.get(idx, [])
                logger.info("Grounding: %d facts loaded, distributed to %d agents", len(grounding_facts), len(selected_agents))
            except Exception as exc:
                logger.warning("Grounding failed, continuing without: %s", exc)
                for agent in selected_agents:
                    agent["grounding_facts"] = []

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
                phase_data=_build_activation_phase_data(
                    activation_result=activation_result,
                    representative_count=len(activation_result["representatives"]),
                    individual_responses=individual_responses,
                ),
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

            # === Phase 3.5: Network Propagation (Swarm Intelligence) ===
            propagation_result = None
            stigmergy_board = StigmergyBoard()
            prediction_market = None
            emergence_tracker = EmergenceTracker()

            try:
                # Load edges for selected agents
                edge_result = await session.execute(
                    select(SocialEdge).where(SocialEdge.population_id == pop_id)
                )
                edges_db = edge_result.scalars().all()
                edges = [
                    {
                        "agent_id": e.agent_id,
                        "target_id": e.target_id,
                        "strength": e.strength,
                    }
                    for e in edges_db
                    if e.agent_id in selected_agent_ids and e.target_id in selected_agent_ids
                ]

                # Prepare responses with agent_id
                responses_with_ids = []
                for agent, resp in zip(selected_agents, activation_result["responses"]):
                    responses_with_ids.append({
                        **resp,
                        "agent_id": agent["id"],
                    })

                await sse_manager.publish(simulation_id, "network_propagation_started", {
                    "agent_count": len(selected_agents),
                    "edge_count": len(edges),
                })

                async def on_propagation_timestep(record):
                    await sse_manager.publish(simulation_id, "propagation_timestep", {
                        "timestep": record.timestep,
                        "opinion_distribution": record.opinion_distribution,
                        "entropy": record.entropy,
                        "cluster_count": record.cluster_count,
                        "max_delta": record.max_delta,
                    })

                propagation_result = await run_network_propagation(
                    agents=selected_agents,
                    initial_responses=responses_with_ids,
                    edges=edges,
                    theme=theme,
                    max_timesteps=12,
                    confidence_threshold=0.5,
                    on_timestep=on_propagation_timestep,
                )

                # Stigmergy: extract topics from agent concerns
                for resp in responses_with_ids:
                    concern = resp.get("concern", "")
                    if concern:
                        # Simple topic extraction from concerns
                        for keyword in ["財源", "格差", "負担", "教育", "生活", "経済", "安全", "環境", "雇用", "福祉"]:
                            if keyword in concern:
                                stigmergy_board.deposit(
                                    resp.get("agent_id", ""),
                                    keyword,
                                    intensity=resp.get("confidence", 0.5),
                                )

                # Compute independence weights and re-aggregate
                cluster_dicts = [
                    {"member_ids": c.member_ids, "size": c.size}
                    for c in propagation_result.clusters
                ]
                independence_weights = _apply_independence_re_aggregation(
                    activation_result, cluster_dicts, edges,
                    selected_agent_ids, selected_agents,
                )
                activation_record.phase_data = _build_activation_phase_data(
                    activation_result=activation_result,
                    representative_count=len(activation_result["representatives"]),
                    individual_responses=individual_responses,
                )

                # Prediction Market (with independence-weighted bets + adaptive liquidity)
                # Design Decision: デフォルトでは pre-propagation stance を使用。
                # 各エージェントの独立した判断を予測市場に反映するため。
                # use_post_propagation=True で社会的影響後のスタンスに切替可能。
                pm_config = _get_prediction_market_config(settings.load_population_mix_config())
                outcomes = list(activation_result["aggregation"]["stance_distribution"].keys())
                if outcomes and not pm_config["use_post_propagation"]:
                    prediction_market = PredictionMarket(outcomes=outcomes, adaptive_b=True)
                    for agent, resp in zip(selected_agents, activation_result["responses"]):
                        stance = resp.get("stance", "中立")
                        raw_confidence = resp.get("confidence", 0.5)
                        calibrated_confidence = platt_recalibrate(raw_confidence)
                        ind_w = independence_weights.get(agent["id"], 1.0)
                        if stance in outcomes:
                            prediction_market.submit_bet(agent["id"], stance, calibrated_confidence, weight=ind_w)

                # Emergence tracking from propagation history
                for ts_record in propagation_result.timestep_history:
                    emergence_tracker.record_timestep({
                        "timestep": ts_record.timestep,
                        "opinions": ts_record.opinions,
                        "agent_ids": selected_agent_ids,
                    })

                # Save propagation result
                propagation_record = SocietyResult(
                    id=str(uuid.uuid4()),
                    simulation_id=simulation_id,
                    population_id=pop_id,
                    layer="network_propagation",
                    phase_data={
                        "converged": propagation_result.converged,
                        "total_timesteps": propagation_result.total_timesteps,
                        "cluster_count": len(propagation_result.clusters),
                        "clusters": [
                            {"label": c.label, "size": c.size, "centroid": c.centroid}
                            for c in propagation_result.clusters
                        ],
                        "echo_chamber": propagation_result.metrics.get("echo_chamber", {}),
                        "stigmergy_topics": [
                            {"topic": t.topic, "intensity": t.intensity}
                            for t in stigmergy_board.get_salient_topics(top_k=10)
                        ],
                        "prediction_market": prediction_market.get_prices() if prediction_market else {},
                        "phase_transitions": emergence_tracker.detect_phase_transitions(),
                        "tipping_points": emergence_tracker.detect_tipping_points(),
                        "aggregation_pre_independence": activation_result.get(
                            "aggregation_pre_independence"
                        ),
                        "aggregation_post_independence": activation_result["aggregation"],
                        "independence_re_aggregation": _build_independence_reaggregation_summary(
                            activation_result
                        ),
                    },
                    usage={},
                )
                session.add(propagation_record)

                # Update activation responses with propagated opinions
                stance_updates = []
                if propagation_result and propagation_result.final_opinions:
                    for i, opinion in enumerate(propagation_result.final_opinions):
                        if i < len(activation_result["responses"]) and i < len(selected_agents):
                            new_stance = _convert_opinion_to_stance(opinion)
                            old_stance = activation_result["responses"][i].get("stance", "")
                            activation_result["responses"][i]["propagated_stance"] = new_stance
                            activation_result["responses"][i]["opinion_vector"] = opinion
                            if new_stance != old_stance:
                                stance_updates.append({
                                    "agent_id": selected_agents[i]["id"],
                                    "stance": new_stance,
                                })

                # Post-propagation prediction market (use_post_propagation=True の場合のみ)
                if outcomes and pm_config["use_post_propagation"]:
                    prediction_market = PredictionMarket(outcomes=outcomes, adaptive_b=True)
                    for agent, resp in zip(selected_agents, activation_result["responses"]):
                        stance = resp.get("propagated_stance", resp.get("stance", "中立"))
                        raw_confidence = resp.get("confidence", 0.5)
                        calibrated_confidence = platt_recalibrate(raw_confidence)
                        ind_w = independence_weights.get(agent["id"], 1.0)
                        if stance in outcomes:
                            prediction_market.submit_bet(agent["id"], stance, calibrated_confidence, weight=ind_w)

                await sse_manager.publish(simulation_id, "network_propagation_completed", {
                    "converged": propagation_result.converged,
                    "total_timesteps": propagation_result.total_timesteps,
                    "cluster_count": len(propagation_result.clusters),
                    "clusters": [
                        {"label": c.label, "size": c.size, "centroid": c.centroid}
                        for c in propagation_result.clusters
                    ],
                    "echo_chamber": propagation_result.metrics.get("echo_chamber", {}),
                    "stance_updates": stance_updates,
                    "aggregation_pre_independence": activation_result.get(
                        "aggregation_pre_independence"
                    ),
                    "independence_weighting_applied": activation_result["aggregation"].get(
                        "independence_weighting_applied", False
                    ),
                    "independence_re_aggregation": _build_independence_reaggregation_summary(
                        activation_result
                    ),
                    "aggregation": activation_result["aggregation"],
                })

                logger.info(
                    "Network propagation completed: %d timesteps, converged=%s, %d clusters",
                    propagation_result.total_timesteps,
                    propagation_result.converged,
                    len(propagation_result.clusters),
                )

            except Exception as exc:
                logger.warning("Network propagation failed, continuing without: %s", exc)

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

            # === Phase 4.5: Validation Registration ===
            survey_comparison = None
            try:
                from src.app.services.society.validation_pipeline import register_result, auto_compare
                survey_data_dir = settings.config_dir / "grounding" / "survey_data"
                stance_dist = activation_result["aggregation"].get("stance_distribution", {})
                # テーマカテゴリを推定（grounding_facts からカテゴリを取得、なければテーマから推定）
                theme_category = _estimate_theme_category(theme, grounding_facts)
                validation_record = await register_result(
                    session,
                    simulation_id=simulation_id,
                    theme=theme,
                    theme_category=theme_category,
                    distribution=stance_dist,
                )
                survey_comparison = await auto_compare(
                    session, validation_record, str(survey_data_dir)
                )
                if survey_comparison:
                    await sse_manager.publish(simulation_id, "validation_comparison_completed", {
                        "kl_divergence": survey_comparison.get("kl_divergence"),
                        "emd": survey_comparison.get("emd"),
                        "best_match_source": survey_comparison.get("best_match_source"),
                        "matched_survey_count": len(survey_comparison.get("matched_surveys", [])),
                    })
                logger.info("Validation registration completed for simulation %s", simulation_id)
            except (FileNotFoundError, ImportError) as exc:
                logger.error("Validation registration failed (system error): %s", exc)
            except (ValueError, KeyError) as exc:
                logger.warning("Validation registration failed (data issue): %s", exc)
            except Exception as exc:
                logger.warning("Validation registration failed, continuing: %s", exc, exc_info=True)

            # === Phase 4.6: Demographic Analysis ===
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

            # Enrich meeting participants with cluster-based counter-arguments
            if propagation_result and propagation_result.clusters:
                enrich_meeting_with_clusters(
                    meeting_participants,
                    propagation_result.clusters,
                    responses_with_ids,
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

            # === Phase 5.05: Prediction Market Resolution ===
            if prediction_market:
                try:
                    synthesis = meeting_result.get("synthesis", {})
                    majority_stance = synthesis.get("majority_stance", "")
                    if majority_stance and majority_stance in [o for o in prediction_market._outcomes]:
                        payoffs = prediction_market.resolve(majority_stance)
                        brier = prediction_market.compute_brier_score(majority_stance)
                        logger.info("Prediction market resolved: Brier=%.3f", brier)
                except Exception as exc:
                    logger.warning("Prediction market resolution failed: %s", exc)

            # === Phase 5.1: Deliberation Quality Assessment ===
            dqi_overall_score = None
            try:
                meeting_rounds = meeting_result.get("rounds", [])
                dqi_result = compute_dqi(meeting_rounds)
                opinion_change = measure_opinion_change(meeting_rounds)
                dqi_data = {
                    "dqi": dqi_result,
                    "opinion_change": opinion_change,
                }
                dqi_society_result = SocietyResult(
                    id=str(uuid.uuid4()),
                    simulation_id=simulation_id,
                    population_id=pop_id,
                    layer="deliberation_quality",
                    phase_data=dqi_data,
                    usage={},
                )
                session.add(dqi_society_result)
                dqi_overall_score = dqi_result.get("overall_dqi")
            except Exception as exc:
                logger.warning("DQI evaluation failed: %s", exc)

            # === Phase 5.5: Provenance 構築 ===
            quality_metrics = {m["metric_name"]: m["score"] for m in eval_metrics}
            if dqi_overall_score is not None:
                quality_metrics["dqi_overall"] = dqi_overall_score

            provenance = build_provenance(
                population_size=len(agents),
                selected_count=len(selected_agents),
                effective_sample_size=activation_result["aggregation"].get(
                    "effective_sample_size", float(len(selected_agents))
                ),
                activation_params={"temperature": 0.5},
                meeting_params={
                    "num_rounds": 3,
                    "participants": len(meeting_participants),
                },
                quality_metrics=quality_metrics,
                seed=sim.seed,
                survey_comparison=survey_comparison,
            )

            # Augment provenance with network propagation data
            if propagation_result:
                provenance["network_propagation"] = {
                    "model": "Bounded Confidence (Hegselmann-Krause) + Friedkin-Johnsen",
                    "max_timesteps": 12,
                    "actual_timesteps": propagation_result.total_timesteps,
                    "converged": propagation_result.converged,
                    "cluster_count": len(propagation_result.clusters),
                    "echo_chamber": propagation_result.metrics.get("echo_chamber", {}),
                }

            # === Phase 5.5: Gap Explanation + Narrative Report ===
            # Explain activation-meeting gap
            propagation_data_for_gap = None
            if propagation_result:
                propagation_data_for_gap = {
                    "converged": propagation_result.converged,
                    "total_timesteps": propagation_result.total_timesteps,
                    "clusters": [
                        {"label": c.label, "size": c.size, "centroid": c.centroid, "member_ids": c.member_ids}
                        for c in propagation_result.clusters
                    ],
                    "echo_chamber": propagation_result.metrics.get("echo_chamber", {}),
                    "timestep_history": [
                        {"timestep": ts.timestep, "opinion_distribution": ts.opinion_distribution}
                        for ts in propagation_result.timestep_history
                    ],
                }

            gap_explanation = explain_activation_meeting_gap(
                aggregation=activation_result["aggregation"],
                synthesis=meeting_result.get("synthesis", {}),
                meeting_participants=meeting_participants,
                propagation_data=propagation_data_for_gap,
            )

            # Prepare cluster data for v2 narrative
            narrative_clusters = None
            if propagation_result and propagation_result.clusters:
                narrative_clusters = [
                    {"label": c.label, "size": c.size, "centroid": c.centroid, "member_ids": c.member_ids}
                    for c in propagation_result.clusters
                ]

            narrative = generate_narrative(
                selected_agents,
                activation_result["responses"],
                meeting_result.get("synthesis", {}),
                activation_result["aggregation"],
                demographic_analysis,
                meeting_rounds=meeting_result.get("rounds"),
                provenance=provenance,
                clusters=narrative_clusters,
            )

            # Enrich narrative with gap explanation
            narrative["gap_explanation"] = gap_explanation

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
                    "aggregation_pre_independence": activation_result.get(
                        "aggregation_pre_independence"
                    ),
                    "aggregation": activation_result["aggregation"],
                    "independence_re_aggregation": _build_independence_reaggregation_summary(
                        activation_result
                    ),
                    "evaluation": eval_data,
                    "meeting": meeting_report,
                    "usage": total_usage,
                },
                "provenance": provenance,
            }
            await session.commit()

            await sse_manager.publish(simulation_id, "society_completed", {
                "simulation_id": simulation_id,
                "aggregation_pre_independence": activation_result.get(
                    "aggregation_pre_independence"
                ),
                "aggregation": activation_result["aggregation"],
                "independence_re_aggregation": _build_independence_reaggregation_summary(
                    activation_result
                ),
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
