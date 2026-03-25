"""介入テストフェーズ

旧 meta_orchestrator.py から移植。
反復ループで介入策をテストし、最良の結果を選択する。
"""

import logging
from dataclasses import dataclass, field

from src.app.services.meta_intervention_planner import plan_interventions, select_intervention
from src.app.services.meta_score import (
    compute_objective_score,
    evaluate_stop_condition,
)
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


@dataclass
class InterventionResult:
    """介入テストの結果"""

    cycles: list[dict] = field(default_factory=list)
    best_cycle: dict = field(default_factory=dict)
    interventions: list[dict] = field(default_factory=list)
    convergence_score: float = 0.0
    usage: dict = field(default_factory=dict)


async def run_intervention(
    session,
    sim,
    context: dict,
    max_cycles: int = 3,
    target_score: float = 0.8,
) -> InterventionResult:
    """反復ループで介入策をテストする。

    Args:
        session: DB セッション
        sim: Simulation モデル
        context: 前フェーズからの引き継ぎデータ
            - theme: 分析テーマ
            - pulse_result: SocietyPulse の結果
            - issues: 抽出されたイシュー
        max_cycles: 最大サイクル数
        target_score: 目標スコア（到達で停止）
    """
    theme = context.get("theme", sim.prompt_text)
    pulse_result = context.get("pulse_result", {})
    issues = context.get("issues", [])
    simulation_id = sim.id

    logger.info("Starting intervention loop for %s (max_cycles=%d)", simulation_id, max_cycles)

    await sse_manager.publish(simulation_id, "phase_changed", {
        "phase": "intervention",
        "max_cycles": max_cycles,
    })

    cycles = []
    best_cycle = {"cycle": 0, "score": 0.0}
    all_interventions = []
    current_intervention = None

    for cycle_idx in range(max_cycles):
        logger.info("Cycle %d/%d for %s", cycle_idx + 1, max_cycles, simulation_id)

        await sse_manager.publish(simulation_id, "intervention_cycle", {
            "cycle": cycle_idx,
            "total": max_cycles,
            "intervention": current_intervention,
        })

        # スコア計算
        score = compute_objective_score(
            aggregation=pulse_result.get("aggregation", {}),
            evaluation=pulse_result.get("evaluation", {}),
            issues=issues,
            intervention=current_intervention,
        )

        cycle_data = {
            "cycle": cycle_idx,
            "score": score,
            "intervention": current_intervention,
            "aggregation_summary": pulse_result.get("aggregation", {}),
        }
        cycles.append(cycle_data)

        # 最良サイクルの更新
        if score > best_cycle.get("score", 0):
            best_cycle = cycle_data

        # 停止判定
        should_stop = evaluate_stop_condition(
            scores=[c["score"] for c in cycles],
            target_score=target_score,
        )

        if should_stop:
            logger.info("Stop condition met at cycle %d (score=%.3f)", cycle_idx, score)
            break

        # 次サイクル用の介入を計画（最終サイクルでなければ）
        if cycle_idx < max_cycles - 1:
            candidates = await plan_interventions(
                theme=theme,
                issues=issues,
                current_score=score,
            )
            all_interventions.extend(candidates)

            current_intervention = select_intervention(candidates)

    convergence_score = cycles[-1]["score"] if cycles else 0.0

    await sse_manager.publish(simulation_id, "intervention_completed", {
        "total_cycles": len(cycles),
        "best_score": best_cycle.get("score", 0),
        "convergence_score": convergence_score,
    })

    logger.info(
        "Intervention completed for %s: %d cycles, best_score=%.3f",
        simulation_id, len(cycles), best_cycle.get("score", 0),
    )

    return InterventionResult(
        cycles=cycles,
        best_cycle=best_cycle,
        interventions=all_interventions,
        convergence_score=convergence_score,
        usage={},
    )
