"""Society オーケストレータ: Population→選抜→活性化→ネットワーク伝播→評価→結果保存

Swarm Intelligence Pipeline:
  Population → Network → Selection → Grounding → Activation
  → Network Propagation (Bounded Confidence + Friedkin-Johnsen)
  → Stigmergy → Prediction Market → Echo Chamber Detection
  → Representative Selection (from propagated opinions)
  → Meeting → Evaluation → Narrative → Memory/Graph Evolution
"""

import hashlib
import inspect
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.app.config import settings
from src.app.database import async_session
from src.app.models.agent_profile import AgentProfile
from src.app.models.evaluation_result import EvaluationResult
from src.app.models.population import Population
from src.app.models.simulation import Simulation
from src.app.models.social_edge import SocialEdge
from src.app.models.society_result import SocietyResult
from src.app.services.graph_activity import (
    GraphActivityCreate,
    persist_graph_activity_events,
    propagation_changes_to_graph_events,
)
from src.app.services.scenario_pair_status import refresh_scenario_pair_status
from src.app.services.society.activation_layer import _aggregate_opinions, run_activation
from src.app.services.society.agent_selector import select_agents
from src.app.services.society.calibration import platt_recalibrate
from src.app.services.society.data_grounding import distribute_facts_to_agents, load_grounding_facts
from src.app.services.society.deliberation_quality import compute_dqi, measure_opinion_change
from src.app.services.society.demographic_analyzer import analyze_demographics
from src.app.services.society.emergence_tracker import EmergenceTracker
from src.app.services.society.evaluation import evaluate_society_simulation
from src.app.services.society.graph_evolution import (
    evolve_social_graph,
    relationship_changes_to_graph_events,
)
from src.app.services.society.meeting_layer import enrich_meeting_with_clusters, run_meeting
from src.app.services.society.meeting_report import generate_meeting_report
from src.app.services.society.memory_compressor import update_agent_memories
from src.app.services.society.narrative_generator import generate_narrative
from src.app.services.society.network_generator import generate_network
from src.app.services.society.network_propagation import (
    _convert_opinion_to_stance,
    run_network_propagation,
)
from src.app.services.society.output_validator import explain_activation_meeting_gap
from src.app.services.society.population_generator import (
    generate_population,
    get_default_population_size,
    validate_population_size,
)
from src.app.services.society.prediction_market import PredictionMarket
from src.app.services.society.provenance import build_provenance
from src.app.services.society.representative_selector import select_representatives
from src.app.services.society.statistical_inference import compute_independence_weights
from src.app.services.society.stigmergy_service import StigmergyBoard
from src.app.services.society.survey_anchor import (
    inject_anchor_prior_stances,
    resolve_anchor_distribution,
    resolve_and_apply_anchor,
)
from src.app.services.society.theme_category import (
    ANCHOR_MIN_CONFIDENCE,
    CONFIDENCE_PER_KEYWORD,
    MVP_CATEGORIES,
    ThemeCategoryEstimate,
)
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

DEFAULT_POPULATION_KEY_PARAM = "default_population_key"
DEFAULT_POPULATION_SOURCE = "census_default"
DEFAULT_POPULATION_GENERATOR_VERSION = 1

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "economy": ["経済", "景気", "物価", "金利", "賃金", "雇用", "収入", "GDP", "インフレ", "デフレ", "財政", "税"],
    "politics": ["政治", "選挙", "外交", "政党", "国会", "法案", "政策", "内閣", "議会"],
    "security": ["防衛", "安全保障", "自衛隊", "軍事", "安保", "テロ", "有事"],
    "environment": ["環境", "エネルギー", "原発", "再生可能", "脱炭素", "気候", "温暖化"],
    "social": ["社会", "福祉", "教育", "医療", "介護", "少子化", "高齢", "年金", "生活"],
}


def _make_layer_record(
    simulation_id: str,
    population_id: str | None,
    layer: str,
    phase_data: dict,
    usage: dict | None = None,
) -> SocietyResult:
    """SocietyResult レイヤレコードを生成する共通ファクトリ（id 採番と usage 既定を集約）。"""
    return SocietyResult(
        id=str(uuid.uuid4()),
        simulation_id=simulation_id,
        population_id=population_id,
        layer=layer,
        phase_data=phase_data,
        usage=usage or {},
    )


def _estimate_theme_category(
    theme: str,
    grounding_facts: list[dict] | None = None,
    override: str | None = None,
) -> ThemeCategoryEstimate:
    """テーマ文やグラウンディングファクトからテーマカテゴリを推定する。

    優先順位: override > grounding_facts > keyword_match > fallback(unknown)
    """
    # 1. override 最優先
    if override is not None and override in _CATEGORY_KEYWORDS:
        return ThemeCategoryEstimate(
            category=override,
            confidence=1.0,
            source="override",
            is_anchor_eligible=True,
        )

    # 2. grounding_facts にカテゴリ情報があればキーワードより優先
    if grounding_facts:
        for fact in grounding_facts:
            cat = fact.get("theme_category") or fact.get("category")
            if cat and cat in _CATEGORY_KEYWORDS:
                return ThemeCategoryEstimate(
                    category=cat,
                    confidence=0.8,
                    source="grounding_facts",
                    is_anchor_eligible=True,
                )

    # 3. テーマ文からキーワードマッチでカテゴリを推定
    best_category: str | None = None
    best_count = 0
    for category, keywords in _CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in theme)
        if count > best_count:
            best_count = count
            best_category = category

    # キーワード 0 件 → unknown
    if best_count == 0:
        return ThemeCategoryEstimate(
            category="unknown",
            confidence=0.0,
            source="fallback",
            is_anchor_eligible=False,
        )

    confidence = min(1.0, best_count * CONFIDENCE_PER_KEYWORD)
    # MVP カテゴリで confidence が閾値未満の場合はアンカリング禁止
    is_anchor_eligible = not (
        best_category in MVP_CATEGORIES and confidence < ANCHOR_MIN_CONFIDENCE
    )
    return ThemeCategoryEstimate(
        category=best_category,
        confidence=confidence,
        source="keyword_match",
        is_anchor_eligible=is_anchor_eligible,
    )


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


def _extract_representative_updates(
    meeting_participants: list[dict],
    meeting_result: dict,
    activation_responses: list[dict],
) -> list[dict]:
    """Compare representative stances before/after meeting and return changes.

    Reads each citizen_representative's pre-meeting stance from
    activation_responses and compares against the meeting synthesis
    participant summaries. Only returns entries where the stance actually
    changed.

    Returns:
        [{"agent_id": str, "old_stance": str, "new_stance": str}, ...]
    """
    # Build lookup: agent_id -> pre-meeting stance
    resp_map: dict[str, str] = {}
    for r in activation_responses:
        resp_map[r.get("agent_id", "")] = r.get("stance", "中立")

    synthesis = meeting_result.get("synthesis", {})
    # Try to get per-participant final stances from synthesis
    participant_stances = synthesis.get("participant_stances", {})

    updates: list[dict] = []
    for p in meeting_participants:
        if p.get("role") != "citizen_representative":
            continue
        agent_profile = p.get("agent_profile", {})
        agent_id = agent_profile.get("id", "")
        if not agent_id:
            continue

        old_stance = resp_map.get(agent_id, "中立")
        # Check synthesis for participant's final stance
        new_stance = participant_stances.get(agent_id, "")

        # Fallback: if synthesis doesn't have per-participant stances,
        # use the majority_stance for representatives (conservative approach)
        if not new_stance:
            new_stance = synthesis.get("majority_stance", old_stance)

        if new_stance and new_stance != old_stance:
            updates.append({
                "agent_id": agent_id,
                "old_stance": old_stance,
                "new_stance": new_stance,
            })

    return updates


def _serialize_agent_profile(agent: AgentProfile) -> dict:
    """永続化済みの住民をシミュレーション用dictへ変換する。"""
    return {
        "id": agent.id,
        "population_id": agent.population_id,
        "agent_index": agent.agent_index,
        "demographics": agent.demographics,
        "big_five": agent.big_five,
        "values": agent.values,
        "life_event": agent.life_event,
        "contradiction": agent.contradiction,
        "information_source": agent.information_source,
        "information_sources": agent.information_sources,
        "local_context": agent.local_context,
        "hidden_motivation": agent.hidden_motivation,
        "speech_style": agent.speech_style,
        "shock_sensitivity": agent.shock_sensitivity,
        "llm_backend": agent.llm_backend,
        "memory_summary": agent.memory_summary,
        "rolling_summary": agent.rolling_summary,
        "episodes": agent.episodes,
    }


async def _load_population_agents(session, population_id: str) -> list[dict]:
    result = await session.execute(
        select(AgentProfile)
        .where(AgentProfile.population_id == population_id)
        .order_by(AgentProfile.agent_index, AgentProfile.id)
    )
    return [_serialize_agent_profile(agent) for agent in result.scalars().all()]


def _default_population_identity(count: int) -> tuple[str, str, int]:
    """人口生成設定から、再利用キー・決定論的ID・固定seedを作る。"""
    mix_config = settings.load_population_mix_config()
    activation_config = mix_config.get("activation_layer", {})
    generation_spec = {
        "generator_version": DEFAULT_POPULATION_GENERATOR_VERSION,
        "count": count,
        "population": mix_config.get("population", {}),
        "activation_weights": activation_config.get("weights", {}),
    }
    canonical_spec = json.dumps(
        generation_spec,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_spec.encode("utf-8")).hexdigest()
    reuse_key = f"{DEFAULT_POPULATION_SOURCE}:v{DEFAULT_POPULATION_GENERATOR_VERSION}:{digest}"
    population_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"agentai/{reuse_key}"))
    generation_seed = int(digest[:8], 16)
    return reuse_key, population_id, generation_seed


def _is_legacy_default_population(params: dict, count: int) -> bool:
    """旧オーケストレータが自動生成した未マーク人口を識別する。"""
    return params == {"count": count}


async def _find_reusable_default_population(
    session,
    *,
    count: int,
    reuse_key: str,
) -> tuple[str, list[dict]] | None:
    result = await session.execute(
        select(Population)
        .where(
            Population.status == "ready",
            Population.parent_id.is_(None),
            Population.agent_count == count,
        )
        .order_by(Population.created_at.desc(), Population.id)
    )
    exact_matches: list[Population] = []
    legacy_matches: list[Population] = []
    for population in result.scalars().all():
        params = dict(population.generation_params or {})
        if params.get(DEFAULT_POPULATION_KEY_PARAM) == reuse_key:
            exact_matches.append(population)
        elif _is_legacy_default_population(params, count):
            legacy_matches.append(population)

    for population in [*exact_matches, *legacy_matches]:
        agents = await _load_population_agents(session, population.id)
        if len(agents) != count:
            logger.warning(
                "Skipping incomplete reusable population %s: expected=%d actual=%d",
                population.id,
                count,
                len(agents),
            )
            continue

        params = dict(population.generation_params or {})
        if params.get(DEFAULT_POPULATION_KEY_PARAM) != reuse_key:
            population.generation_params = {
                **params,
                "source": DEFAULT_POPULATION_SOURCE,
                DEFAULT_POPULATION_KEY_PARAM: reuse_key,
            }
            await session.commit()
            logger.info("Adopted legacy population %s as the census default", population.id)
        else:
            logger.info("Reusing census default population %s", population.id)
        return population.id, agents

    return None


async def _create_default_population(
    session,
    *,
    count: int,
    reuse_key: str,
    population_id: str,
    generation_seed: int,
) -> tuple[str, list[dict]]:
    """デフォルト人口を原子的に作成し、競合時は先に作られた人口を使う。"""
    agents = await generate_population(population_id, count, seed=generation_seed)
    if len(agents) != count:
        raise RuntimeError(
            f"Generated population size mismatch: expected={count} actual={len(agents)}"
        )

    population = Population(
        id=population_id,
        agent_count=count,
        generation_params={
            "count": count,
            "seed": generation_seed,
            "source": DEFAULT_POPULATION_SOURCE,
            DEFAULT_POPULATION_KEY_PARAM: reuse_key,
        },
        status="ready",
    )
    session.add(population)
    session.add_all([AgentProfile(**agent_data) for agent_data in agents])
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        winner = await _find_reusable_default_population(
            session,
            count=count,
            reuse_key=reuse_key,
        )
        if winner is not None:
            return winner
        raise

    logger.info("Created census default population %s with %d agents", population_id, count)
    return population_id, agents


async def _get_or_create_population(
    session,
    population_id: str | None = None,
    count: int | None = None,
    seed: int | None = None,
    *,
    strict: bool = False,
) -> tuple[str, list[dict]]:
    """明示人口または共有デフォルト人口を取得し、未作成時だけ生成する。

    strict=True の場合、population_id が無効なときはエラーを返す（フォールバックしない）。
    """
    resolved_count = get_default_population_size() if count is None else validate_population_size(count)

    if population_id:
        pop = await session.get(Population, population_id)
        if pop and pop.status == "ready":
            agents = await _load_population_agents(session, population_id)
            if agents:
                return population_id, agents
            if strict:
                raise ValueError(
                    f"Population {population_id} has no agent profiles"
                )
        elif strict:
            if pop is None:
                raise ValueError(f"Population not found: {population_id}")
            else:
                raise ValueError(
                    f"Population {population_id} is not ready (status={pop.status})"
                )
        else:
            logger.warning(
                "Population %s not usable (exists=%s, status=%s), generating new population",
                population_id,
                pop is not None,
                getattr(pop, "status", None),
            )

    reuse_key, default_population_id, generation_seed = _default_population_identity(
        resolved_count
    )
    reusable = await _find_reusable_default_population(
        session,
        count=resolved_count,
        reuse_key=reuse_key,
    )
    if reusable is not None:
        return reusable

    if seed is not None:
        logger.debug(
            "Ignoring simulation seed %s for shared population; canonical seed=%s",
            seed,
            generation_seed,
        )
    return await _create_default_population(
        session,
        count=resolved_count,
        reuse_key=reuse_key,
        population_id=default_population_id,
        generation_seed=generation_seed,
    )


async def _save_network(
    session,
    agents: list[dict],
    population_id: str,
    seed: int | None = None,
) -> None:
    """人口にネットワークがなければ生成し、既存ネットワークは再利用する。"""
    result = await session.execute(
        select(func.count())
        .select_from(SocialEdge)
        .where(SocialEdge.population_id == population_id)
    )
    existing_edge_count = int(result.scalar() or 0)
    if existing_edge_count > 0:
        logger.info(
            "Reusing %d social edges for population %s",
            existing_edge_count,
            population_id,
        )
        return

    edges = await generate_network(agents, population_id, seed=seed)
    for edge_data in edges:
        edge = SocialEdge(**edge_data)
        session.add(edge)
    await session.commit()


async def _load_population_edges(session, population_id: str) -> list[dict]:
    """population_id に紐づくエッジを読み込む。"""
    edge_result = await session.execute(
        select(SocialEdge).where(SocialEdge.population_id == population_id)
        .order_by(SocialEdge.agent_id, SocialEdge.target_id)
    )
    edges_db = edge_result.scalars().all()
    return [
        {
            "agent_id": e.agent_id,
            "target_id": e.target_id,
            "strength": e.strength,
        }
        for e in edges_db
    ]


async def _load_selected_social_edges(
    session, population_id: str, selected_ids: set[str]
) -> list[dict]:
    """選抜エージェント同士（両端が selected_ids に含まれる）のソーシャルエッジを、
    フロント表示用の形（id/source/target/relation_type/strength）で返す。

    ソーシャル構造はデモグラから生成され活性化（意見形成）より前に確定・永続化
    されているため、選抜完了直後に送出できる。/social-graph エンドポイントと
    同じ両端フィルタのパターン。
    """
    if not selected_ids:
        return []
    edge_result = await session.execute(
        select(SocialEdge).where(
            SocialEdge.population_id == population_id,
            SocialEdge.agent_id.in_(selected_ids),
            SocialEdge.target_id.in_(selected_ids),
        )
    )
    return [
        {
            "id": e.id or f"edge-{e.agent_id}-{e.target_id}",
            "source": e.agent_id,
            "target": e.target_id,
            "relation_type": e.relation_type,
            "strength": e.strength,
        }
        for e in edge_result.scalars().all()
    ]


def _phase_grounding(theme: str, selected_agents: list[dict]) -> list:
    """Phase 2.7: grounding facts をロードし各エージェントへ配布する（selected_agents を変異）。"""
    grounding_facts = []
    try:
        grounding_facts = load_grounding_facts(theme)
        agent_facts = distribute_facts_to_agents(selected_agents, grounding_facts)
        for idx, agent in enumerate(selected_agents):
            agent["grounding_facts"] = agent_facts.get(idx, [])
        logger.info(
            "Grounding: %d facts loaded, distributed to %d agents",
            len(grounding_facts), len(selected_agents),
        )
    except Exception as exc:
        logger.warning("Grounding failed, continuing without: %s", exc)
        for agent in selected_agents:
            agent["grounding_facts"] = []
    return grounding_facts


def _phase_theme_anchor(
    theme: str,
    grounding_facts: list,
    simulation_id: str,
    diagnostic_cfg: dict | None = None,
):
    """Phase 2.8: theme_category 推定とアンカー分布の事前準備。

    returns: (survey_data_dir, theme_estimate, anchor_distribution)
    """
    survey_data_dir = settings.config_dir / "grounding" / "survey_data"
    theme_estimate = _estimate_theme_category(theme, grounding_facts)
    logger.info(
        "Theme category estimated: category=%s confidence=%.2f source=%s anchor_eligible=%s",
        theme_estimate.category, theme_estimate.confidence,
        theme_estimate.source, theme_estimate.is_anchor_eligible,
    )

    anchor_distribution: dict[str, float] | None = None
    anchor_source = "none"
    anchor_survey_ids: list[str] = []
    if theme_estimate.is_anchor_eligible or (diagnostic_cfg or {}).get("anchor_source"):
        try:
            anchor_distribution, anchor_source, anchor_survey_ids = resolve_anchor_distribution(
                theme,
                theme_estimate.category,
                diagnostic_cfg=diagnostic_cfg,
                survey_data_dir=survey_data_dir,
            )
            if anchor_distribution:
                logger.info(
                    "Anchor distribution pre-loaded for category=%s source=%s",
                    theme_estimate.category, anchor_source,
                )
        except Exception as exc:
            logger.warning(
                "Anchor distribution pre-load failed (sim=%s): %s",
                simulation_id, exc, exc_info=True,
            )
    return survey_data_dir, theme_estimate, anchor_distribution, anchor_source, anchor_survey_ids


def _diagnostic_config(sim: Simulation) -> dict:
    metadata = dict(sim.metadata_json or {})
    diagnostic = metadata.get("diagnostic")
    return dict(diagnostic) if isinstance(diagnostic, dict) else {}


def _maybe_inject_anchor_prior(
    selected_agents: list[dict],
    anchor_distribution: dict[str, float] | None,
    diagnostic_cfg: dict,
    seed: int | None,
) -> None:
    if not diagnostic_cfg.get("per_agent_anchor"):
        return
    if anchor_distribution is None:
        raise ValueError("diagnostic.per_agent_anchor requires a resolved anchor_distribution")
    # Diagnostic prior semantics: this is a category-level prior from train surveys,
    # not an eval-theme-specific ground truth distribution.
    inject_anchor_prior_stances(selected_agents, anchor_distribution, seed=seed)


def _phase_episodic_memory(
    theme: str, theme_estimate: ThemeCategoryEstimate, selected_agents: list[dict]
) -> None:
    """Phase 2.9: 二層メモリ Layer B のエピソード選択（selected_agents を変異）。"""
    from src.app.services.society.accuracy_config import is_enabled as _acc_is_enabled
    if _acc_is_enabled("episodic_memory"):
        from src.app.services.society.memory_compressor import select_relevant_episodes
        for agent in selected_agents:
            agent["_relevant_episodes"] = select_relevant_episodes(
                agent.get("episodes"), theme, theme_estimate.category, top_k=3,
            )


@dataclass
class SocietyRunContext:
    """run_society のフェーズ間で受け渡す状態を集約する可変コンテキスト。

    フェーズ抽出の進行に合わせてフィールドを追加していく。各フェーズは ctx を
    読み書きし、run_society 本体は ctx の組み立てとフェーズ呼び出しに専念する。
    """

    simulation_id: str
    theme: str
    pop_id: str
    selected_agents: list[dict]
    activation_result: dict
    diagnostic_cfg: dict = field(default_factory=dict)
    eval_metrics: list = field(default_factory=list)
    eval_data: dict = field(default_factory=dict)
    demographic_analysis: dict = field(default_factory=dict)
    dqi_overall_score: float | None = None
    # Network Propagation フェーズの出力（下流フェーズが参照）
    propagation_result: object | None = None
    prediction_market: object | None = None
    edges: list = field(default_factory=list)
    responses_with_ids: list = field(default_factory=list)
    # Validation フェーズの出力（Provenance 構築で参照）
    survey_comparison: dict | None = None
    anchor_application: object | None = None
    # Meeting Layer フェーズの出力（下流フェーズが参照）
    meeting_participants: list = field(default_factory=list)
    meeting_result: dict | None = None
    meeting_report: dict | None = None
    # Provenance フェーズの出力（Narrative / 完了メタデータで参照）
    provenance: dict | None = None


async def _phase_evaluation(ctx: "SocietyRunContext", session) -> None:
    """Phase 4: 社会シミュレーションの評価指標を計算・永続化し ctx に保存する。"""
    eval_metrics = await evaluate_society_simulation(
        ctx.selected_agents, ctx.activation_result["responses"],
    )

    for metric in eval_metrics:
        eval_record = EvaluationResult(
            id=str(uuid.uuid4()),
            simulation_id=ctx.simulation_id,
            metric_name=metric["metric_name"],
            score=metric["score"],
            details=metric["details"],
            baseline_type=metric.get("baseline_type"),
            baseline_score=metric.get("baseline_score"),
        )
        session.add(eval_record)

    eval_data = {m["metric_name"]: m["score"] for m in eval_metrics}
    eval_record_society = _make_layer_record(
        simulation_id=ctx.simulation_id,
        population_id=ctx.pop_id,
        layer="evaluation",
        phase_data={"metrics": eval_data},
        usage={},
    )
    session.add(eval_record_society)

    await sse_manager.publish(ctx.simulation_id, "society_evaluation_completed", {
        "metrics": eval_data,
    })

    ctx.eval_metrics = eval_metrics
    ctx.eval_data = eval_data


def _phase_demographics(ctx: "SocietyRunContext", session) -> None:
    """Phase 4.6: 人口統計分析を計算・永続化し ctx に保存する。"""
    demographic_analysis = analyze_demographics(
        ctx.selected_agents, ctx.activation_result["responses"],
    )
    demo_record = _make_layer_record(
        simulation_id=ctx.simulation_id,
        population_id=ctx.pop_id,
        layer="demographic_analysis",
        phase_data=demographic_analysis,
        usage={},
    )
    session.add(demo_record)
    ctx.demographic_analysis = demographic_analysis


def _phase_deliberation_quality(ctx: "SocietyRunContext", session, meeting_result: dict) -> None:
    """Phase 5.1: 熟議品質指標(DQI)を計算・永続化し ctx.dqi_overall_score に保存する。"""
    ctx.dqi_overall_score = None
    try:
        meeting_rounds = meeting_result.get("rounds", [])
        dqi_result = compute_dqi(meeting_rounds)
        opinion_change = measure_opinion_change(meeting_rounds)
        dqi_data = {
            "dqi": dqi_result,
            "opinion_change": opinion_change,
        }
        dqi_society_result = _make_layer_record(
            simulation_id=ctx.simulation_id,
            population_id=ctx.pop_id,
            layer="deliberation_quality",
            phase_data=dqi_data,
            usage={},
        )
        session.add(dqi_society_result)
        ctx.dqi_overall_score = dqi_result.get("overall_dqi")
    except Exception as exc:
        logger.warning("DQI evaluation failed: %s", exc)


async def _phase_network_propagation(
    ctx: "SocietyRunContext",
    session,
    activation_record,
    individual_responses: list,
) -> None:
    """Phase 3.5: ネットワーク伝播(群知能)を実行し ctx に結果を保存する。

    エッジを読み込んで意見伝播・スティグマジー・予測市場・創発検知を実行し、
    network_propagation レイヤを永続化する。失敗時は握り潰して伝播なしで継続。
    ctx.propagation_result / prediction_market / edges / responses_with_ids を更新する。
    """
    simulation_id = ctx.simulation_id
    theme = ctx.theme
    pop_id = ctx.pop_id
    selected_agents = ctx.selected_agents
    activation_result = ctx.activation_result
    selected_agent_ids = [a["id"] for a in selected_agents]

    propagation_result = None
    stigmergy_board = StigmergyBoard()
    prediction_market = None
    emergence_tracker = EmergenceTracker()
    edges: list = []
    responses_with_ids: list = []

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
            graph_events = propagation_changes_to_graph_events(
                getattr(record, "changes", []),
                phase="network_propagation",
                round=record.timestep,
                stance_source_key="target_id",
            )
            await persist_graph_activity_events(
                session,
                simulation_id,
                graph_events,
            )
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
        propagation_record = _make_layer_record(
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
            # Update persisted phase_data with post-propagation prices
            propagation_record.phase_data["prediction_market"] = prediction_market.get_prices()

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

    ctx.propagation_result = propagation_result
    ctx.prediction_market = prediction_market
    ctx.edges = edges
    ctx.responses_with_ids = responses_with_ids


async def _phase_validation(
    ctx: "SocietyRunContext",
    session,
    theme_estimate,
    survey_data_dir,
) -> None:
    """Phase 4.5: 検証レジストリ登録と survey 比較を行い ctx.survey_comparison を更新する。

    theme_estimate / survey_data_dir は前処理(Phase 2.8)の出力を明示引数で受け取る。
    失敗時は握り潰して継続する（survey_comparison は None のまま）。
    """
    simulation_id = ctx.simulation_id
    theme = ctx.theme
    activation_result = ctx.activation_result

    survey_comparison = None
    try:
        from src.app.services.society.validation_pipeline import (
            auto_compare,
            build_distribution_prediction_payload,
            register_prediction_evaluation,
            register_result,
        )
        stance_dist = activation_result["aggregation"].get("stance_distribution", {})
        validation_record = await register_result(
            session,
            simulation_id=simulation_id,
            theme=theme,
            theme_category=theme_estimate.category,
            distribution=stance_dist,
            theme_category_estimate=theme_estimate,
        )
        survey_comparison = await auto_compare(
            session, validation_record, str(survey_data_dir)
        )
        actual_payload = None
        if survey_comparison:
            best_survey = next(
                (
                    survey
                    for survey in survey_comparison.get("matched_surveys", [])
                    if survey.get("source") == survey_comparison.get("best_match_source")
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
            source="society_orchestrator",
            predicted_payload=build_distribution_prediction_payload(
                activation_result["aggregation"],
                prediction_market_distribution=(
                    ctx.prediction_market.get_prices() if ctx.prediction_market else None
                ),
            ),
            actual_payload=actual_payload,
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
        logger.error("Validation registration failed (system error) sim=%s: %s", simulation_id, exc)
    except (ValueError, KeyError) as exc:
        logger.warning("Validation registration failed (data issue) sim=%s: %s", simulation_id, exc)
    except Exception as exc:
        logger.warning("Validation registration failed, continuing sim=%s: %s", simulation_id, exc, exc_info=True)

    ctx.survey_comparison = survey_comparison


async def _phase_persona(ctx: "SocietyRunContext") -> None:
    """Phase 4.8: activation 後にペルソナナラティブを生成し selected_agents を更新する。

    generate_... は agents を in-place 変異しつつ同一リストを返すため ctx 参照は
    保たれるが、将来の戻り値差し替えに備え ctx.selected_agents も更新する。
    失敗時は握り潰して継続する。
    """
    try:
        from src.app.services.society.persona_generator import (
            generate_persona_narratives_post_activation,
        )
        await sse_manager.publish(ctx.simulation_id, "persona_generation_started", {
            "agent_count": len(ctx.selected_agents),
        })
        ctx.selected_agents = await generate_persona_narratives_post_activation(
            ctx.selected_agents, ctx.activation_result["responses"], ctx.theme,
        )
        persona_count = sum(1 for a in ctx.selected_agents if a.get("persona_narrative"))
        logger.info(
            "Post-activation persona narratives: %d/%d generated",
            persona_count, len(ctx.selected_agents),
        )
    except Exception as exc:
        logger.warning("Post-activation persona generation failed, continuing: %s", exc)


async def _phase_meeting(ctx: "SocietyRunContext", session, total_usage: dict) -> None:
    """Phase 5: 代表者会議を実行し meeting レイヤを永続化する。

    propagation_result があればクラスタベースの反論で参加者を enrich する。
    total_usage は run_society 全体の累積 dict を明示引数で受け取り in-place 加算する。
    ctx.meeting_participants / meeting_result / meeting_report を更新する。
    """
    simulation_id = ctx.simulation_id
    theme = ctx.theme
    pop_id = ctx.pop_id
    selected_agents = ctx.selected_agents
    activation_result = ctx.activation_result
    propagation_result = ctx.propagation_result
    responses_with_ids = ctx.responses_with_ids

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

    meeting_kwargs = {
        "simulation_id": simulation_id,
        "num_rounds": 3,
    }
    if "session" in inspect.signature(run_meeting).parameters:
        meeting_kwargs["session"] = session
    meeting_result = await run_meeting(
        meeting_participants,
        theme,
        **meeting_kwargs,
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

    meeting_record = _make_layer_record(
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

    ctx.meeting_participants = meeting_participants
    ctx.meeting_result = meeting_result
    ctx.meeting_report = meeting_report


async def _phase_meeting_feedback(ctx: "SocietyRunContext", session, sim_seed) -> None:
    """Phase 5.025: 会議結果を母集団へフィードバック伝播する(フラグ ON 時のみ)。

    representative_updates が生じた場合のみ post_feedback_* レイヤを永続化する。
    propagation_result が無い/フラグ OFF/更新なしの場合は何もしない。失敗時は握り潰す。
    """
    simulation_id = ctx.simulation_id
    pop_id = ctx.pop_id
    selected_agents = ctx.selected_agents
    propagation_result = ctx.propagation_result
    meeting_participants = ctx.meeting_participants
    meeting_result = ctx.meeting_result
    responses_with_ids = ctx.responses_with_ids
    edges = ctx.edges

    feedback_result = None
    try:
        from src.app.services.society.accuracy_config import is_enabled
        if is_enabled("meeting_feedback_propagation") and propagation_result:
            await sse_manager.publish(simulation_id, "meeting_feedback_started", {
                "representative_count": len(meeting_participants),
            })

            representative_updates = _extract_representative_updates(
                meeting_participants, meeting_result, responses_with_ids,
            )

            if representative_updates:
                from src.app.services.society.network_propagation import (
                    run_meeting_feedback_propagation,
                )
                feedback_result = await run_meeting_feedback_propagation(
                    agents=selected_agents,
                    edges=edges,
                    representative_updates=representative_updates,
                    activation_responses=responses_with_ids,
                    seed=sim_seed,
                )

                await sse_manager.publish(simulation_id, "meeting_feedback_timestep", {
                    "changed_count": len(feedback_result["changed_agents"]),
                })

                # Re-run evaluation with post-feedback responses
                fb_responses = feedback_result["feedback_responses"]
                post_fb_eval = await evaluate_society_simulation(
                    selected_agents, fb_responses,
                )
                post_fb_eval_data = {m["metric_name"]: m["score"] for m in post_fb_eval}

                # Re-run demographic analysis
                post_fb_demographics = analyze_demographics(
                    selected_agents, fb_responses,
                )

                # Rebuild PredictionMarket with post-feedback opinions
                fb_stances = list({r["stance"] for r in fb_responses})
                if fb_stances:
                    post_fb_market = PredictionMarket(outcomes=fb_stances, adaptive_b=True)
                    for resp in fb_responses:
                        stance = resp.get("stance", "中立")
                        if stance in fb_stances:
                            post_fb_market.submit_bet(
                                resp["agent_id"], stance,
                                resp.get("confidence", 0.5),
                            )

                    # Resolve with meeting majority_stance
                    synthesis = meeting_result.get("synthesis", {})
                    majority_stance = synthesis.get("majority_stance", "")
                    post_fb_brier = None
                    if majority_stance and majority_stance in fb_stances:
                        post_fb_market.resolve(majority_stance)
                        post_fb_brier = post_fb_market.compute_brier_score(majority_stance)

                # Save post-feedback results as separate layers
                fb_eval_record = _make_layer_record(
                    simulation_id=simulation_id,
                    population_id=pop_id,
                    layer="post_feedback_evaluation",
                    phase_data={"metrics": post_fb_eval_data},
                    usage={},
                )
                session.add(fb_eval_record)

                fb_demo_record = _make_layer_record(
                    simulation_id=simulation_id,
                    population_id=pop_id,
                    layer="post_feedback_demographics",
                    phase_data=post_fb_demographics,
                    usage={},
                )
                session.add(fb_demo_record)

                fb_propagation_record = _make_layer_record(
                    simulation_id=simulation_id,
                    population_id=pop_id,
                    layer="post_feedback_propagation",
                    phase_data={
                        "propagation_record": feedback_result["propagation_record"],
                        "changed_agents": feedback_result["changed_agents"],
                        "market_prices": post_fb_market.get_prices() if fb_stances else {},
                        "brier_score": post_fb_brier,
                    },
                    usage={},
                )
                session.add(fb_propagation_record)

            await sse_manager.publish(simulation_id, "meeting_feedback_completed", {
                "total_changed": len(feedback_result["changed_agents"]) if feedback_result else 0,
            })
    except (ValueError, ImportError) as exc:
        logger.warning("Meeting feedback propagation skipped: %s", exc)
    except Exception as exc:
        logger.warning("Meeting feedback propagation failed: %s", exc, exc_info=True)


def _phase_prediction_market_resolution(ctx: "SocietyRunContext") -> None:
    """Phase 5.05: 会議の多数派スタンスで予測市場を清算する(market への副作用のみ)。"""
    prediction_market = ctx.prediction_market
    if prediction_market:
        try:
            synthesis = ctx.meeting_result.get("synthesis", {})
            majority_stance = synthesis.get("majority_stance", "")
            if majority_stance and majority_stance in [o for o in prediction_market._outcomes]:
                prediction_market.resolve(majority_stance)
                brier = prediction_market.compute_brier_score(majority_stance)
                logger.info("Prediction market resolved: Brier=%.3f", brier)
        except Exception as exc:
            logger.warning("Prediction market resolution failed: %s", exc)


def _phase_provenance(
    ctx: "SocietyRunContext",
    agents: list,
    theme_estimate,
    anchor_applied: bool,
    sim_seed,
) -> None:
    """Phase 5.5: provenance(再現性メタデータ)を構築し ctx.provenance に保存する。

    agents(全母集団) / theme_estimate / anchor_applied / sim_seed は前処理・setup の
    出力を明示引数で受け取る。
    """
    selected_agents = ctx.selected_agents
    activation_result = ctx.activation_result
    propagation_result = ctx.propagation_result

    quality_metrics = {m["metric_name"]: m["score"] for m in ctx.eval_metrics}
    if ctx.dqi_overall_score is not None:
        quality_metrics["dqi_overall"] = ctx.dqi_overall_score

    provenance = build_provenance(
        population_size=len(agents),
        selected_count=len(selected_agents),
        effective_sample_size=activation_result["aggregation"].get(
            "effective_sample_size", float(len(selected_agents))
        ),
        activation_params={"temperature": 0.5},
        meeting_params={
            "num_rounds": 3,
            "participants": len(ctx.meeting_participants),
        },
        quality_metrics=quality_metrics,
        seed=sim_seed,
        survey_comparison=ctx.survey_comparison,
    )

    # Augment provenance with theme_category anchoring provenance
    provenance["theme_category_anchoring"] = {
        "category": theme_estimate.category,
        "confidence": theme_estimate.confidence,
        "source": theme_estimate.source,
        "is_anchor_eligible": theme_estimate.is_anchor_eligible,
        "anchor_applied": anchor_applied,
    }

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

    ctx.provenance = provenance


def _phase_narrative(ctx: "SocietyRunContext", session) -> None:
    """Phase 5.5: activation-meeting ギャップ説明とナラティブを生成し narrative レイヤを永続化する。"""
    activation_result = ctx.activation_result
    meeting_result = ctx.meeting_result
    propagation_result = ctx.propagation_result

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
        meeting_participants=ctx.meeting_participants,
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
        ctx.selected_agents,
        activation_result["responses"],
        meeting_result.get("synthesis", {}),
        activation_result["aggregation"],
        ctx.demographic_analysis,
        meeting_rounds=meeting_result.get("rounds"),
        provenance=ctx.provenance,
        clusters=narrative_clusters,
    )

    # Enrich narrative with gap explanation
    narrative["gap_explanation"] = gap_explanation

    narrative_record = _make_layer_record(
        simulation_id=ctx.simulation_id,
        population_id=ctx.pop_id,
        layer="narrative",
        phase_data=narrative,
        usage={},
    )
    session.add(narrative_record)


async def _phase_persistent_society(ctx: "SocietyRunContext", session, theme_estimate) -> None:
    """Phase 6: エージェント記憶の圧縮とソーシャルグラフ進化を行い社会を永続化する。"""
    simulation_id = ctx.simulation_id
    pop_id = ctx.pop_id
    selected_agents = ctx.selected_agents

    from src.app.services.society.accuracy_config import AccuracyConfig as _AccuracyConfig
    _acc_flags = _AccuracyConfig(settings.load_population_mix_config())
    _mem_llm = None
    if _acc_flags.is_enabled("rolling_summary"):
        from src.app.llm.multi_client import multi_llm_client as _mem_llm
    await update_agent_memories(
        session, selected_agents, ctx.activation_result["responses"],
        meeting_result=ctx.meeting_result,
        theme=ctx.theme,
        theme_category=theme_estimate.category,
        simulation_id=simulation_id,
        llm_client=_mem_llm,
        accuracy_flags=_acc_flags,
    )

    evolution_result = await evolve_social_graph(
        session, pop_id, ctx.meeting_result, ctx.meeting_participants,
    )
    await persist_graph_activity_events(
        session,
        simulation_id,
        relationship_changes_to_graph_events(
            evolution_result,
            len(ctx.meeting_result.get("rounds", [])),
        ),
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


async def _phase_time_axis(ctx: "SocietyRunContext", session, sim) -> bool:
    """Phase 6(Wondrous Crayon): 時間軸予測パイプライン(フラグ ON 時のみ)。

    sim.metadata_json に time_axis_result / time_axis_error を追記し、実行可否を返す。
    """
    from src.app.services.society.accuracy_config import AccuracyConfig as _AccuracyConfig
    _acc_flags = _AccuracyConfig(settings.load_population_mix_config())
    if not _acc_flags.is_enabled("time_axis_orchestrator"):
        return False

    simulation_id = ctx.simulation_id
    pop_id = ctx.pop_id
    try:
        from src.app.services.society.time_axis_runner import (
            run_time_axis_pipeline,
        )
        edge_rows = (await session.execute(
            select(SocialEdge).where(SocialEdge.population_id == pop_id)
        )).scalars().all()
        edges_list: list[tuple] = [
            (e.agent_id, e.target_id) for e in edge_rows
        ]
        base_responses: list[dict] = []
        for agent, resp in zip(
            ctx.selected_agents, ctx.activation_result.get("responses", [])
        ):
            base_responses.append({
                **resp,
                "agent_id": agent["id"],
            })
        time_axis_report = await run_time_axis_pipeline(
            simulation_id=simulation_id,
            base_responses=base_responses,
            base_edges=edges_list,
            theme=ctx.theme,
            sse_manager=sse_manager,
        )
        sim.metadata_json = {
            **dict(sim.metadata_json or {}),
            "time_axis_result": time_axis_report,
        }
        await session.commit()
        return True
    except Exception as time_axis_exc:
        logger.exception(
            "time-axis pipeline failed for sim %s", simulation_id
        )
        sim.metadata_json = {
            **dict(sim.metadata_json or {}),
            "time_axis_error": (
                f"{type(time_axis_exc).__name__}: {time_axis_exc}"
            )[:500],
        }
        await session.commit()
        return False


async def run_society(simulation_id: str) -> None:
    """Society モードのメインオーケストレーション。"""
    logger.info("Starting society simulation %s", simulation_id)

    async with async_session() as session:
        sim = await session.get(Simulation, simulation_id)
        if not sim:
            logger.error("Simulation %s not found", simulation_id)
            return

        theme = sim.prompt_text
        scenario_pair_id = getattr(sim, "scenario_pair_id", None)
        diagnostic_cfg = _diagnostic_config(sim)
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        try:
            # === Phase 1: Population ===
            await persist_graph_activity_events(
                session,
                simulation_id,
                [GraphActivityCreate(
                    phase="population",
                    kind="phase_changed",
                    payload={"phase": "population"},
                )],
            )
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
                strict=bool(scenario_pair_id),
            )
            sim.population_id = pop_id
            await session.commit()

            await sse_manager.publish(simulation_id, "population_status", {
                "status": "ready",
                "agent_count": len(agents),
                "population_id": pop_id,
            })

            # ネットワーク生成（バックグラウンド的に）
            await _save_network(session, agents, pop_id, seed=sim.seed)

            # === Phase 2: Selection (network centrality-aware) ===
            all_edges = await _load_population_edges(session, pop_id)
            selected_agents = await select_agents(agents, theme, target_count=100, edges=all_edges)

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
                        for index, agent in enumerate(selected_agents)
                        if agent.get("id")
                    ],
                ],
            )

            # === Phase 2.7: Grounding ===
            grounding_facts = _phase_grounding(theme, selected_agents)

            # === Phase 2.8: theme_category 推定とアンカー事前準備 ===
            (
                survey_data_dir,
                theme_estimate,
                anchor_distribution,
                anchor_source,
                anchor_survey_ids,
            ) = _phase_theme_anchor(
                theme, grounding_facts, simulation_id, diagnostic_cfg=diagnostic_cfg
            )

            # === Phase 2.9: エピソードメモリ選択（二層メモリ Layer B） ===
            _phase_episodic_memory(theme, theme_estimate, selected_agents)

            # === Phase 3: Activation ===
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

            _maybe_inject_anchor_prior(
                selected_agents,
                anchor_distribution,
                diagnostic_cfg,
                sim.seed,
            )
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

            # === Phase 3.1: Survey アンカリング（activation 後・propagation 前）===
            # anchor_distribution が None（not eligible or 調査なし）の場合はスキップ
            stance_dist_pre_anchor = activation_result["aggregation"].get("stance_distribution", {})
            anchor_application = resolve_and_apply_anchor(
                stance_dist_pre_anchor,
                theme,
                theme_estimate.category,
                diagnostic_cfg=diagnostic_cfg,
                survey_data_dir=survey_data_dir,
                anchor_distribution=anchor_distribution,
                anchor_source=anchor_source,
                anchor_survey_ids=anchor_survey_ids,
            )
            anchor_applied = anchor_application.applied
            if anchor_application.anchor_distribution is not None:
                activation_result["aggregation"]["anchor_distribution"] = (
                    anchor_application.anchor_distribution
                )
                activation_result["aggregation"]["anchor_source"] = anchor_application.source
                activation_result["aggregation"]["anchor_survey_ids"] = (
                    anchor_application.source_survey_ids
                )
            if anchor_applied:
                activation_result["aggregation"]["stance_distribution_pre_anchor"] = (
                    anchor_application.pre_distribution
                )
                activation_result["aggregation"]["stance_distribution"] = (
                    anchor_application.post_distribution
                )
                logger.info(
                    "Survey anchor applied: category=%s source=%s",
                    theme_estimate.category,
                    anchor_application.source,
                )

            activation_record = _make_layer_record(
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
                ],
            )

            ctx = SocietyRunContext(
                simulation_id=simulation_id,
                theme=theme,
                pop_id=pop_id,
                selected_agents=selected_agents,
                activation_result=activation_result,
                diagnostic_cfg=diagnostic_cfg,
                anchor_application=anchor_application,
            )

            # === Phase 3.5: Network Propagation (Swarm Intelligence) ===
            await _phase_network_propagation(
                ctx, session, activation_record, individual_responses,
            )

            # === Phase 4: Evaluation ===
            await _phase_evaluation(ctx, session)
            eval_data = ctx.eval_data

            # === Phase 4.5: Validation Registration ===
            await _phase_validation(ctx, session, theme_estimate, survey_data_dir)

            # === Phase 4.6: Demographic Analysis ===
            _phase_demographics(ctx, session)

            # === Phase 4.8: Post-Activation Persona Generation ===
            await _phase_persona(ctx)
            selected_agents = ctx.selected_agents

            # === Phase 5: Meeting Layer ===
            await _phase_meeting(ctx, session, total_usage)
            meeting_result = ctx.meeting_result
            meeting_report = ctx.meeting_report

            # === Phase 5.025: Meeting Feedback Propagation ===
            await _phase_meeting_feedback(ctx, session, sim.seed)

            # === Phase 5.05: Prediction Market Resolution ===
            _phase_prediction_market_resolution(ctx)

            # === Phase 5.1: Deliberation Quality Assessment ===
            _phase_deliberation_quality(ctx, session, meeting_result)

            # === Phase 5.5: Provenance 構築 ===
            _phase_provenance(ctx, agents, theme_estimate, anchor_applied, sim.seed)
            provenance = ctx.provenance

            # === Phase 5.5: Gap Explanation + Narrative Report ===
            _phase_narrative(ctx, session)

            # === Phase 6: Persistent Society (記憶圧縮 + グラフ進化) ===
            await _phase_persistent_society(ctx, session, theme_estimate)

            # === 完了 ===
            sim.status = "completed"
            sim.completed_at = datetime.now(UTC)
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

            # === Wondrous Crayon: 時間軸予測 (フラグ ON 時のみ) ===
            time_axis_available = await _phase_time_axis(ctx, session, sim)

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
                "time_axis_available": time_axis_available,
                "usage": total_usage,
            })
            await persist_graph_activity_events(
                session,
                simulation_id,
                [GraphActivityCreate(
                    phase="completed",
                    round=len(ctx.meeting_result.get("rounds", [])),
                    kind="phase_changed",
                    payload={"phase": "completed"},
                )],
            )

            logger.info("Society simulation %s completed", simulation_id)

        except Exception as e:
            logger.error("Society simulation %s failed: %s", simulation_id, e, exc_info=True)
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
