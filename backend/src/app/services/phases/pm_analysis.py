"""PM分析フェーズ

旧 pm_board_orchestrator.py のラッパー。
3PMペルソナ（戦略/発見/実行）が並列分析し、
チーフPMが統合して11セクション構造を生成する。
"""

import logging
from dataclasses import dataclass, field

from src.app.services.pm_board_orchestrator import run_pm_board

logger = logging.getLogger(__name__)


@dataclass
class PMAnalysisResult:
    """PM分析の結果"""

    analyses: list[dict] = field(default_factory=list)
    synthesis: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    decision_brief: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)


async def run_pm_analysis(
    session,
    sim,
    context: dict,
) -> PMAnalysisResult:
    """PM Board 分析を実行する。

    内部で run_pm_board() を呼び出し、結果を PMAnalysisResult に変換する。

    Args:
        session: DB セッション
        sim: Simulation モデル
        context: 前フェーズからの引き継ぎデータ
            - theme: 分析テーマ
            - document_text: 入力文書（オプション）
            - scenarios: シナリオ候補（multi_perspective の結果等）
    """
    theme = context.get("theme", sim.prompt_text)
    document_text = context.get("document_text", "")
    scenarios = context.get("scenarios", None)
    simulation_id = sim.id

    logger.info("Starting PM analysis for %s", simulation_id)

    raw_result = await run_pm_board(
        session=session,
        simulation_id=simulation_id,
        prompt_text=theme,
        document_text=document_text,
        scenario_candidates=scenarios,
        project_id=getattr(sim, "project_id", None),
    )

    result = PMAnalysisResult(
        analyses=raw_result.get("pm_analyses", []),
        synthesis=raw_result.get("synthesis", {}),
        sections=raw_result.get("sections", {}),
        decision_brief=raw_result.get("decision_brief", {}),
        usage=raw_result.get("usage", {}),
    )

    logger.info("PM analysis completed for %s", simulation_id)
    return result
