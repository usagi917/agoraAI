"""多視点並列分析フェーズ

旧 swarm_orchestrator.py から移植。
複数の視点（perspective）でテーマを並列分析し、
Claim抽出 → クラスタリング → シナリオ集約 を行う。
"""

import asyncio
import copy
import logging
from dataclasses import dataclass, field

from src.app.config import settings
from src.app.services.colony_factory import generate_colony_configs
from src.app.services.simulator import SingleRunSimulator
from src.app.services.claim_extractor import extract_claims
from src.app.services.claim_clusterer import cluster_claims
from src.app.services.aggregator import aggregate_clusters
from src.app.services.swarm_report_generator import generate_swarm_integrated_report
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


@dataclass
class MultiPerspectiveResult:
    """多視点分析の結果"""

    perspectives: list[dict] = field(default_factory=list)
    scenarios: list[dict] = field(default_factory=list)
    agreement_matrix: dict = field(default_factory=dict)
    integrated_report: str = ""
    diversity_score: float = 0.0
    entropy: float = 0.0
    usage: dict = field(default_factory=dict)


async def run_multi_perspective(
    session,
    sim,
    context: dict,
    perspective_count: int = 5,
    max_concurrent: int | None = None,
) -> MultiPerspectiveResult:
    """複数視点で並列分析し、シナリオに集約する。

    Args:
        session: DB セッション
        sim: Simulation モデル
        context: 前フェーズからの引き継ぎデータ
            - theme: 分析テーマ
            - world_state: ワールドステート
            - template_prompts: テンプレートプロンプト
        perspective_count: 視点の数
        max_concurrent: 最大並列数（None の場合は settings から取得）
    """
    if max_concurrent is None:
        max_concurrent = settings.max_concurrent_colonies

    theme = context.get("theme", sim.prompt_text)
    world_state = context.get("world_state", {})
    template_prompts = context.get("template_prompts", {})
    simulation_id = sim.id

    logger.info("Starting multi-perspective analysis for %s (%d perspectives)", simulation_id, perspective_count)

    await sse_manager.publish(simulation_id, "phase_changed", {
        "phase": "multi_perspective",
        "perspective_count": perspective_count,
    })

    # 1. 視点設定の生成
    configs = generate_colony_configs(
        simulation_id=simulation_id,
        profile_name=sim.execution_profile,
        diversity_mode="balanced",
    )
    # perspective_count に合わせて調整
    if len(configs) > perspective_count:
        configs = configs[:perspective_count]

    # 2. 視点ごとに並列実行
    sem = asyncio.Semaphore(max_concurrent)
    total_usage = {"total_tokens": 0}

    async def run_single_perspective(config) -> dict:
        async with sem:
            simulator = SingleRunSimulator(colony_config=config)
            cloned_ws = copy.deepcopy(world_state)
            result = await simulator.run(
                run_id=config.colony_id,
                world_state=cloned_ws,
                session=session,
                template_prompts=template_prompts,
                total_rounds=config.round_count,
                sse_channel=simulation_id,
                prompt_text=theme,
            )
            return {
                "colony_id": config.colony_id,
                "colony_config": config,
                "perspective": config.perspective_label,
                "temperature": config.temperature,
                "adversarial": config.adversarial,
                **result,
            }

    perspective_results_raw = await asyncio.gather(
        *[run_single_perspective(c) for c in configs],
        return_exceptions=True,
    )

    # 成功した結果を収集
    successful_results = []
    for i, result in enumerate(perspective_results_raw):
        if isinstance(result, Exception):
            logger.error("Perspective %s failed: %s", configs[i].colony_id, result)
        else:
            successful_results.append(result)

    if not successful_results:
        logger.warning("All perspectives failed for %s", simulation_id)
        return MultiPerspectiveResult(usage=total_usage)

    await sse_manager.publish(simulation_id, "perspectives_completed", {
        "successful": len(successful_results),
        "failed": len(perspective_results_raw) - len(successful_results),
    })

    # 3. Claim 抽出 → クラスタリング → 集約
    await sse_manager.publish(simulation_id, "phase_changed", {"phase": "aggregation"})

    all_claims = await extract_claims(session, simulation_id, successful_results)
    clusters = await cluster_claims(session, simulation_id, all_claims)
    aggregation = await aggregate_clusters(session, simulation_id, clusters, successful_results)
    await session.commit()

    # 4. 統合レポート生成
    integrated_report = ""
    try:
        integrated_report = await generate_swarm_integrated_report(
            session=session,
            simulation_id=simulation_id,
            prompt_text=theme,
            colony_results=successful_results,
            colony_configs=configs,
            aggregation=aggregation,
        )
    except Exception as e:
        logger.error("Integrated report generation failed: %s", e, exc_info=True)

    # 5. 結果構築
    perspectives = [
        {
            "id": r["colony_id"],
            "label": r.get("perspective", ""),
            "temperature": r.get("temperature", 0.5),
            "adversarial": r.get("adversarial", False),
            "event_count": len(r.get("events", [])),
            "agent_count": len(r.get("agents", {}).get("agents", [])),
        }
        for r in successful_results
    ]

    result = MultiPerspectiveResult(
        perspectives=perspectives,
        scenarios=aggregation.get("scenarios", []),
        agreement_matrix=aggregation.get("agreement_matrix", {}),
        integrated_report=integrated_report,
        diversity_score=aggregation.get("diversity_score", 0.0),
        entropy=aggregation.get("entropy", 0.0),
        usage=total_usage,
    )

    logger.info(
        "Multi-perspective completed for %s: %d perspectives, %d scenarios",
        simulation_id, len(perspectives), len(result.scenarios),
    )

    return result
