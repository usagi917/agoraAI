"""Synthesis フェーズ: Decision Brief 生成 + クロスバリデーション + フルレポート"""

import logging
from dataclasses import dataclass
from typing import Any

from src.app.llm.multi_client import multi_llm_client
from src.app.models.simulation import Simulation
from src.app.services.phases.society_pulse import SocietyPulseResult
from src.app.services.phases.council_deliberation import CouncilResult
from src.app.services.decision_briefing import render_decision_brief_markdown
from src.app.services.meta_score import compute_society_score
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    decision_brief: dict
    agreement_score: float
    content: str
    sections: dict


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_agreement_score(
    society_summary: dict,
    council_synthesis: dict,
) -> float:
    """Society score と Council score を 50:50 で合成して合意度を計算する。"""
    # Society score: average_confidence + consistency + calibration の平均
    aggregation = society_summary.get("aggregation", {}) or {}
    evaluation = society_summary.get("evaluation", {}) or {}

    avg_confidence = _safe_float(aggregation.get("average_confidence"), 0.0)
    consistency = _safe_float(evaluation.get("consistency"), 0.0)
    calibration = _safe_float(evaluation.get("calibration"), 0.0)

    if avg_confidence == 0.0 and consistency == 0.0 and calibration == 0.0:
        return 0.0

    society_score = (avg_confidence + consistency + calibration) / 3

    # Council score: 合意点の数 / (合意点 + 対立点の数) で近似
    consensus_points = council_synthesis.get("consensus_points", []) or []
    disagreement_points = council_synthesis.get("disagreement_points", []) or []
    total_points = len(consensus_points) + len(disagreement_points)
    council_score = len(consensus_points) / total_points if total_points > 0 else 0.5

    return round(society_score * 0.5 + council_score * 0.5, 4)


async def _generate_decision_brief(
    pulse: SocietyPulseResult,
    council: CouncilResult,
    theme: str,
) -> tuple[dict, dict]:
    """LLM を使って Decision Brief を生成する。"""
    multi_llm_client.initialize()

    aggregation = pulse.aggregation
    synthesis = council.synthesis

    system_prompt = (
        "あなたは戦略コンサルタントです。社会調査と評議会議論の結果に基づいて、"
        "意思決定者向けの Decision Brief をJSON形式で作成してください。\n\n"
        "出力JSON:\n"
        "{\n"
        '  "recommendation": "Go | No-Go | 条件付きGo",\n'
        '  "decision_summary": "1-2文の結論要約",\n'
        '  "why_now": "なぜ今この判断をするのか",\n'
        '  "agreement_score": 0.0-1.0,\n'
        '  "agreement_breakdown": {"society": float, "council": float, "synthesis": float},\n'
        '  "key_reasons": [{"reason": "str", "evidence": "str", "confidence": 0.0-1.0, "decision_impact": "str"}],\n'
        '  "guardrails": [{"condition": "str", "status": "met|partially_met|unverified|at_risk", "why_it_matters": "str"}],\n'
        '  "deal_breakers": [{"trigger": "str", "impact": "str", "recommended_response": "str"}],\n'
        '  "critical_unknowns": [{"question": "str", "importance": "str", "how_to_validate": "str", "decision_blocking": true}],\n'
        '  "next_decisions": [{"decision": "str", "owner": "str", "deadline": "str", "input_needed": "str"}],\n'
        '  "recommended_actions": [{"action": "str", "owner": "str", "deadline": "str", "expected_learning": "str", "priority": "high|medium|low"}],\n'
        '  "option_comparison": [{"label": "str", "upside": "str", "downside": "str", "fit": "str", "when_to_choose": "str"}],\n'
        '  "confidence_explainer": "str",\n'
        '  "evidence_gaps": ["str"],\n'
        '  "options": [{"label": "str", "expected_effect": "str", "risk": "str"}],\n'
        '  "strongest_counterargument": "str",\n'
        '  "risk_factors": [{"condition": "str", "impact": "str"}],\n'
        '  "next_steps": ["str"],\n'
        '  "time_horizon": {\n'
        '    "short_term": {"period": "3ヶ月", "prediction": "str"},\n'
        '    "mid_term": {"period": "1年", "prediction": "str"},\n'
        '    "long_term": {"period": "3年", "prediction": "str"}\n'
        '  },\n'
        '  "stakeholder_reactions": [{"group": "str", "reaction": "str", "percentage": int}]\n'
        "}"
    )

    user_prompt = (
        f"テーマ: {theme}\n\n"
        f"社会反応:\n"
        f"- 立場分布: {aggregation.get('stance_distribution', {})}\n"
        f"- 平均信頼度: {aggregation.get('average_confidence', 0)}\n"
        f"- 主な懸念: {aggregation.get('top_concerns', [])}\n\n"
        f"評議会結果:\n"
        f"- 合意点: {synthesis.get('consensus_points', [])}\n"
        f"- 対立点: {synthesis.get('disagreement_points', [])}\n"
        f"- 提言: {synthesis.get('recommendations', [])}\n"
        f"- 総合評価: {synthesis.get('overall_assessment', '')}\n\n"
        f"反証役サマリー: {council.devil_advocate_summary}\n"
        "\n要件:\n"
        "- 最初に結論を出すこと\n"
        "- 結論を支える根拠を3-5件に厳選すること\n"
        "- 条件付き判断なら、その条件と覆るトリガーを明示すること\n"
        "- 不確実性は検証方法まで書くこと\n"
        "- 次のアクションは何が学べるかまで書くこと\n"
    )

    try:
        result, usage = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=4096,
        )

        if isinstance(result, dict):
            return result, usage

        # 文字列の場合はフォールバック
        return _build_fallback_brief(pulse, council), usage

    except Exception as e:
        logger.warning("Decision brief generation failed: %s", e)
        return _build_fallback_brief(pulse, council), {}


def _build_fallback_brief(
    pulse: SocietyPulseResult,
    council: CouncilResult,
) -> dict:
    """LLM 呼び出しが失敗した場合のフォールバック Decision Brief。"""
    aggregation = pulse.aggregation
    stance_dist = aggregation.get("stance_distribution", {})
    avg_conf = _safe_float(aggregation.get("average_confidence"), 0.5)

    # 最多スタンスで推奨を決定
    top_stance = max(stance_dist.items(), key=lambda x: x[1])[0] if stance_dist else "中立"
    if top_stance in ("賛成", "条件付き賛成"):
        recommendation = "条件付きGo"
    elif top_stance in ("反対", "条件付き反対"):
        recommendation = "No-Go"
    else:
        recommendation = "条件付きGo"

    return {
        "recommendation": recommendation,
        "decision_summary": "市民受容は一定あるが、主要な懸念を潰すまでは条件付きで進めるべき。",
        "why_now": "社会反応と評議会の論点が出揃った段階で、追加検証の優先順位を固定するため。",
        "agreement_score": round(avg_conf, 2),
        "agreement_breakdown": {"society": round(avg_conf, 2), "council": 0.5, "synthesis": 0.5},
        "key_reasons": [
            {
                "reason": "社会反応として一定の支持があり、完全な拒否ではない。",
                "evidence": str(aggregation.get("stance_distribution", {})),
                "confidence": round(avg_conf, 2),
                "decision_impact": "即時No-Goではなく条件付き判断に寄せる根拠",
            }
        ],
        "guardrails": [
            {
                "condition": "主要懸念への対策を先に設計できること",
                "status": "unverified",
                "why_it_matters": "懸念を放置すると支持が反転しやすい",
            }
        ],
        "deal_breakers": [
            {
                "trigger": council.devil_advocate_summary or "反対論点が解消されないこと",
                "impact": "条件付きGoからNo-Goへ転じる",
                "recommended_response": "追加設計または段階導入で反証条件を潰す",
            }
        ],
        "critical_unknowns": [
            {
                "question": "主要懸念が実務上どの程度の障害になるか",
                "importance": "最終判断を左右する",
                "how_to_validate": "対象セグメント別に追加ヒアリングする",
                "decision_blocking": True,
            }
        ],
        "next_decisions": [
            {
                "decision": "段階導入で進めるか、前提が整うまで保留するか",
                "owner": "意思決定者",
                "deadline": "次回レビュー",
                "input_needed": "主要懸念への対策案",
            }
        ],
        "recommended_actions": [
            {
                "action": "追加調査で主要懸念の実態を確認する",
                "owner": "調査担当",
                "deadline": "2週間",
                "expected_learning": "条件付きGoの前提が成立するか分かる",
                "priority": "high",
            }
        ],
        "option_comparison": [
            {
                "label": "条件付きで進める",
                "upside": "学習を進めながら判断精度を上げられる",
                "downside": "決定速度は落ちる",
                "fit": "支持はあるが反対論点も残るテーマ",
                "when_to_choose": "主要懸念を短期検証できる場合",
            }
        ],
        "confidence_explainer": "支持は一定あるが、反証役の懸念をまだ十分に潰せていないため中程度の確信度に留まる。",
        "evidence_gaps": ["主要懸念に対する一次情報が不足している"],
        "options": [],
        "strongest_counterargument": council.devil_advocate_summary,
        "risk_factors": [],
        "next_steps": ["追加調査が必要"],
        "time_horizon": {
            "short_term": {"period": "3ヶ月", "prediction": "データ不足"},
            "mid_term": {"period": "1年", "prediction": "データ不足"},
            "long_term": {"period": "3年", "prediction": "データ不足"},
        },
        "stakeholder_reactions": [],
    }


def _build_unified_markdown(
    theme: str,
    *,
    pulse: SocietyPulseResult,
    council: CouncilResult,
    decision_brief: dict,
    agreement_score: float,
) -> str:
    """統合レポートの Markdown を生成する。"""
    aggregation = pulse.aggregation
    lines = [
        "# 統合シミュレーションレポート",
        "",
        render_decision_brief_markdown(decision_brief),
        "",
        "---",
        "",
    ]

    # 社会反応サマリー
    lines.extend([
        "## 社会反応サマリー",
        f"- 合意度: {agreement_score * 100:.1f}%",
        f"- 平均信頼度: {_safe_float(aggregation.get('average_confidence')) * 100:.1f}%",
    ])
    stance_dist = aggregation.get("stance_distribution", {})
    for stance, ratio in (stance_dist or {}).items():
        lines.append(f"- {stance}: {_safe_float(ratio) * 100:.1f}%")
    lines.append("")

    # 評議会議論ハイライト
    lines.append("## 評議会議論ハイライト")
    synthesis = council.synthesis
    consensus = synthesis.get("consensus_points", [])
    if consensus:
        lines.append("### 合意点")
        for point in consensus:
            lines.append(f"- {point}")
    disagreements = synthesis.get("disagreement_points", [])
    if disagreements:
        lines.append("### 対立点")
        for d in disagreements:
            if isinstance(d, dict):
                lines.append(f"- {d.get('topic', '')}")
            else:
                lines.append(f"- {d}")
    lines.append("")

    # ステークホルダー反応
    stakeholders = decision_brief.get("stakeholder_reactions", [])
    if stakeholders:
        lines.append("## ステークホルダー反応")
        for s in stakeholders:
            lines.append(f"- {s.get('group', '')}: {s.get('reaction', '')} ({s.get('percentage', 0)}%)")
        lines.append("")

    # リスクファクター
    risks = decision_brief.get("risk_factors", [])
    if risks:
        lines.append("## リスクファクター")
        for r in risks:
            lines.append(f"- {r.get('condition', '')}: {r.get('impact', '')}")
        lines.append("")

    # 時間軸予測
    time_horizon = decision_brief.get("time_horizon", {})
    if time_horizon:
        lines.append("## 時間軸予測")
        for period_key in ("short_term", "mid_term", "long_term"):
            period = time_horizon.get(period_key, {})
            if period:
                lines.append(f"- {period.get('period', '')}: {period.get('prediction', '')}")
        lines.append("")

    # 次の検証ステップ
    next_steps = decision_brief.get("next_steps", [])
    if next_steps:
        lines.append("## 次の検証ステップ")
        for step in next_steps:
            lines.append(f"- {step}")
        lines.append("")

    return "\n".join(lines).strip()


async def run_synthesis(
    session: Any,
    sim: Simulation,
    pulse: SocietyPulseResult,
    council: CouncilResult,
    theme: str,
) -> SynthesisResult:
    """Synthesis フェーズを実行する。

    Decision Brief 生成 + クロスバリデーション + フルレポート Markdown 生成。
    """
    simulation_id = sim.id

    # Decision Brief 生成
    decision_brief, brief_usage = await _generate_decision_brief(pulse, council, theme)

    # 合意度計算
    society_summary = {
        "aggregation": pulse.aggregation,
        "evaluation": pulse.evaluation,
    }
    agreement_score = compute_agreement_score(society_summary, council.synthesis)

    # decision_brief に合意度を上書き（計算値を優先）
    decision_brief["agreement_score"] = agreement_score

    # フルレポート Markdown 生成
    content = _build_unified_markdown(
        theme,
        pulse=pulse,
        council=council,
        decision_brief=decision_brief,
        agreement_score=agreement_score,
    )

    # セクション構造
    sections = {
        "decision_brief": decision_brief,
        "society_summary": {
            "aggregation": pulse.aggregation,
            "evaluation": pulse.evaluation,
        },
        "council": {
            "participants": council.participants,
            "synthesis": council.synthesis,
            "devil_advocate_summary": council.devil_advocate_summary,
        },
    }

    await sse_manager.publish(simulation_id, "report_completed", {
        "report_length": len(content),
        "agreement_score": agreement_score,
    })

    return SynthesisResult(
        decision_brief=decision_brief,
        agreement_score=agreement_score,
        content=content,
        sections=sections,
    )
