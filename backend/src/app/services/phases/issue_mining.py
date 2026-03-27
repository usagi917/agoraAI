"""イシュー抽出フェーズ

旧 society_first_orchestrator.py から移植。
社会調査の結果からイシューを抽出し、
ランク付け・介入比較を行う。
"""

import logging
from dataclasses import dataclass, field

from src.app.services.society.issue_miner import (
    build_intervention_comparison,
    mine_issue_candidates,
    select_top_issues,
)
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


@dataclass
class IssueMiningResult:
    """イシュー抽出の結果"""

    issues: list[dict] = field(default_factory=list)
    selected_issues: list[dict] = field(default_factory=list)
    intervention_comparison: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


async def run_issue_mining(
    session,
    sim,
    context: dict,
    max_issues: int = 3,
) -> IssueMiningResult:
    """社会調査結果からイシューを抽出する。

    Args:
        session: DB セッション
        sim: Simulation モデル
        context: 前フェーズからの引き継ぎデータ
            - theme: 分析テーマ
            - pulse_result: SocietyPulse の結果
        max_issues: 抽出するイシューの最大数
    """
    theme = context.get("theme", sim.prompt_text)
    pulse_result = context.get("pulse_result", {})
    simulation_id = sim.id

    logger.info("Starting issue mining for %s", simulation_id)

    await sse_manager.publish(simulation_id, "phase_changed", {
        "phase": "issue_mining",
    })

    aggregation = pulse_result.get("aggregation", {})

    # 1. イシュー候補を抽出
    issues = await mine_issue_candidates(
        theme=theme,
        aggregation=aggregation,
    )

    # 2. トップイシューを選択
    selected = select_top_issues(issues, max_count=max_issues)

    # 3. 介入比較
    intervention_comparison = await build_intervention_comparison(
        theme=theme,
        issues=selected,
    )

    await sse_manager.publish(simulation_id, "issue_mining_completed", {
        "issue_count": len(issues),
        "selected_count": len(selected),
    })

    logger.info(
        "Issue mining completed for %s: %d candidates, %d selected",
        simulation_id, len(issues), len(selected),
    )

    return IssueMiningResult(
        issues=issues,
        selected_issues=selected,
        intervention_comparison=intervention_comparison,
        usage={},
    )
