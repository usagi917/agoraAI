"""Synthesis フェーズ: Decision Brief 生成 + クロスバリデーション + フルレポート"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from src.app.llm.multi_client import multi_llm_client
from src.app.models.simulation import Simulation
from src.app.services.phases.society_pulse import SocietyPulseResult
from src.app.services.phases.council_deliberation import CouncilResult
from src.app.services.decision_briefing import render_decision_brief_markdown
from src.app.services.react_reporter import react_generate_decision_brief
from src.app.services.society.conversation_highlights import extract_conversation_highlights
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
    # 合意/対立点がゼロの場合は society_score のみを使用（0.5にフォールバックしない）
    consensus_points = council_synthesis.get("consensus_points", []) or []
    disagreement_points = council_synthesis.get("disagreement_points", []) or []
    total_points = len(consensus_points) + len(disagreement_points)
    if total_points > 0:
        council_score = len(consensus_points) / total_points
    else:
        # Council データなし → society_score のみで判定
        return round(society_score, 4)

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

        if isinstance(result, dict) and not result.get("_error"):
            return result, usage

        # 文字列の場合: 二次パース試行
        if isinstance(result, str) and result.strip():
            logger.warning("Decision brief returned string, attempting secondary parse (len=%d)", len(result))
            # markdown fences 除去
            cleaned = re.sub(r"```(?:json)?\s*\n?", "", result)
            cleaned = cleaned.replace("```", "").strip()
            # thinking tags 除去
            cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
            # JSON 抽出
            first_brace = cleaned.find("{")
            last_brace = cleaned.rfind("}")
            if first_brace >= 0 and last_brace > first_brace:
                try:
                    parsed = json.loads(cleaned[first_brace:last_brace + 1])
                    if isinstance(parsed, dict):
                        logger.info("Decision brief recovered from string via secondary parse")
                        return parsed, usage
                except json.JSONDecodeError:
                    pass

        logger.error(
            "Decision brief LLM returned non-dict, using data-driven fallback. Raw type=%s, preview=%.200s",
            type(result).__name__, str(result)[:200],
        )
        return _build_fallback_brief(pulse, council), usage

    except Exception as e:
        logger.error("Decision brief generation failed: %s: %s", type(e).__name__, e)
        return _build_fallback_brief(pulse, council), {}


def _build_fallback_brief(
    pulse: SocietyPulseResult,
    council: CouncilResult,
) -> dict:
    """LLM 呼び出しが失敗した場合のデータ駆動フォールバック Decision Brief。

    ハードコード値ではなく、実際の society pulse と council データから構築する。
    """
    logger.warning("Building data-driven fallback Decision Brief")

    aggregation = pulse.aggregation
    stance_dist = aggregation.get("stance_distribution", {})
    avg_conf = _safe_float(aggregation.get("average_confidence"), 0.5)
    top_concerns = aggregation.get("top_concerns", [])
    top_priorities = aggregation.get("top_priorities", [])
    synthesis = council.synthesis or {}
    consensus_points = synthesis.get("consensus_points", []) or []
    disagreement_points = synthesis.get("disagreement_points", []) or []
    recommendations = synthesis.get("recommendations", []) or []
    overall_assessment = synthesis.get("overall_assessment", "") or ""
    scenarios = synthesis.get("scenarios", []) or []

    # 最多スタンスで推奨を決定
    top_stance = max(stance_dist.items(), key=lambda x: x[1])[0] if stance_dist else "中立"
    if top_stance in ("賛成", "条件付き賛成"):
        recommendation = "条件付きGo" if avg_conf < 0.7 else "Go"
    elif top_stance in ("反対", "条件付き反対"):
        recommendation = "No-Go"
    else:
        recommendation = "条件付きGo"

    # スタンス分布から decision_summary を構築
    dist_parts = [f"{s}: {v*100:.0f}%" for s, v in stance_dist.items()]
    dist_text = "、".join(dist_parts) if dist_parts else "データなし"
    decision_summary = f"社会反応は{dist_text}。{overall_assessment[:100]}" if overall_assessment else f"社会反応は{dist_text}。懸念を検証した上で判断が必要。"

    # agreement_breakdown を実データから計算
    total_points = len(consensus_points) + len(disagreement_points)
    council_score = len(consensus_points) / total_points if total_points > 0 else avg_conf
    synthesis_score = (avg_conf + council_score) / 2

    # key_reasons を実データから構築
    key_reasons = []
    if stance_dist:
        key_reasons.append({
            "reason": f"社会反応のスタンス分布: {dist_text}",
            "evidence": str(stance_dist),
            "confidence": round(avg_conf, 2),
            "decision_impact": f"最多スタンス「{top_stance}」に基づく判断根拠",
        })
    for cp in consensus_points[:2]:
        key_reasons.append({
            "reason": f"評議会合意点: {cp}",
            "evidence": "評議会での討論結果",
            "confidence": round(council_score, 2),
            "decision_impact": "合意形成された論点",
        })

    # evidence_gaps を disagreement_points と concerns から構築
    evidence_gaps = []
    for dp in disagreement_points[:3]:
        topic = dp.get("topic", dp) if isinstance(dp, dict) else str(dp)
        evidence_gaps.append(f"対立点「{topic}」の検証が必要")
    for concern in top_concerns[:2]:
        evidence_gaps.append(f"懸念「{concern}」に対する一次データが不足")
    if not evidence_gaps:
        evidence_gaps.append("評議会データが不十分なため追加調査が必要")

    # next_steps を recommendations と concerns から構築
    next_steps = []
    for rec in recommendations[:3]:
        next_steps.append(rec)
    if top_concerns and not next_steps:
        next_steps.append(f"主要懸念「{top_concerns[0]}」の実態調査")
    if not next_steps:
        next_steps.append("追加の社会調査を実施し、データの解像度を上げる")

    # time_horizon を scenarios と stance_dist から構築
    def _horizon_prediction(period: str, scenarios_data: list) -> str:
        if scenarios_data:
            top = scenarios_data[0]
            name = top.get("name", "") if isinstance(top, dict) else str(top)
            prob = top.get("probability", 0) if isinstance(top, dict) else 0
            return f"主要シナリオ「{name}」（確率{prob*100:.0f}%）が想定される" if name else f"スタンス分布に基づく推移を注視"
        if stance_dist:
            return f"現時点のスタンス（{top_stance} {stance_dist.get(top_stance, 0)*100:.0f}%）が{period}後も維持される可能性が高い"
        return "データ収集中のため予測困難"

    return {
        "recommendation": recommendation,
        "decision_summary": decision_summary[:200],
        "why_now": "社会反応と評議会の論点が出揃った段階で、次のアクションの優先順位を固定するため。",
        "agreement_score": round(synthesis_score, 2),
        "agreement_breakdown": {
            "society": round(avg_conf, 2),
            "council": round(council_score, 2),
            "synthesis": round(synthesis_score, 2),
        },
        "key_reasons": key_reasons or [{"reason": "データ収集中", "evidence": "N/A", "confidence": 0.0, "decision_impact": "判断保留"}],
        "guardrails": [
            {
                "condition": top_concerns[0] if top_concerns else "主要懸念への対策を先に設計できること",
                "status": "unverified",
                "why_it_matters": top_concerns[1] if len(top_concerns) > 1 else "懸念を放置すると支持が反転しやすい",
            }
        ],
        "deal_breakers": [
            {
                "trigger": council.devil_advocate_summary or "反対論点が解消されないこと",
                "impact": "条件付きGoからNo-Goへ転じる",
                "recommended_response": recommendations[0] if recommendations else "追加設計または段階導入で反証条件を潰す",
            }
        ],
        "critical_unknowns": [
            {
                "question": evidence_gaps[0] if evidence_gaps else "主要懸念の実態",
                "importance": "最終判断を左右する",
                "how_to_validate": "対象セグメント別に追加ヒアリングする",
                "decision_blocking": True,
            }
        ],
        "next_decisions": [
            {
                "decision": next_steps[0] if next_steps else "追加調査の実施",
                "owner": "意思決定者",
                "deadline": "次回レビュー",
                "input_needed": "主要懸念への対策案",
            }
        ],
        "recommended_actions": [
            {
                "action": step,
                "owner": "調査担当",
                "deadline": "2週間",
                "expected_learning": f"「{step}」の結果から判断精度が向上する",
                "priority": "high" if i == 0 else "medium",
            }
            for i, step in enumerate(next_steps[:3])
        ],
        "option_comparison": [
            {
                "label": "条件付きで進める",
                "upside": "学習を進めながら判断精度を上げられる",
                "downside": "決定速度は落ちる",
                "fit": f"支持率{stance_dist.get(top_stance, 0)*100:.0f}%で反対論点も残るテーマ" if stance_dist else "情報不足時",
                "when_to_choose": "主要懸念を短期検証できる場合",
            }
        ],
        "confidence_explainer": overall_assessment[:200] if overall_assessment else f"平均信頼度{avg_conf*100:.0f}%。{'合意点' + str(len(consensus_points)) + '件' if consensus_points else '合意点未確認'}、{'対立点' + str(len(disagreement_points)) + '件' if disagreement_points else '対立点未確認'}。",
        "evidence_gaps": evidence_gaps,
        "options": [
            {"label": s.get("name", ""), "expected_effect": s.get("description", ""), "risk": ", ".join(s.get("key_factors", []))}
            for s in scenarios[:3]
        ] if scenarios else [],
        "strongest_counterargument": council.devil_advocate_summary,
        "risk_factors": [
            {"condition": concern, "impact": "社会的受容性に影響"}
            for concern in top_concerns[:3]
        ],
        "next_steps": next_steps,
        "time_horizon": {
            "short_term": {"period": "3ヶ月", "prediction": _horizon_prediction("3ヶ月", scenarios[:1])},
            "mid_term": {"period": "1年", "prediction": _horizon_prediction("1年", scenarios[1:2] if len(scenarios) > 1 else scenarios[:1])},
            "long_term": {"period": "3年", "prediction": _horizon_prediction("3年", scenarios[2:3] if len(scenarios) > 2 else [])},
        },
        "stakeholder_reactions": [],
    }


async def _build_narrative_report(
    theme: str,
    *,
    pulse: SocietyPulseResult,
    council: CouncilResult,
    decision_brief: dict,
    agreement_score: float,
) -> str:
    """LLM を使ってナラティブ形式のレポートを生成する。

    箇条書きではなく、読み物として成立するレポートを目指す。
    エージェントの引用、信念変化ストーリー、議論のドラマを含む。
    """
    aggregation = pulse.aggregation

    # 会話ハイライトを抽出
    highlights = await extract_conversation_highlights(
        council.rounds, council.synthesis, theme,
    )

    # ナラティブ生成用のデータを構造化
    stance_dist = aggregation.get("stance_distribution", {})
    dist_text = "、".join(f"{s}: {_safe_float(v)*100:.0f}%" for s, v in stance_dist.items())

    consensus = council.synthesis.get("consensus_points", []) or []
    disagreements = council.synthesis.get("disagreement_points", []) or []
    recommendations = council.synthesis.get("recommendations", []) or []

    key_quotes = highlights.get("key_quotes", [])
    belief_journeys = highlights.get("belief_journeys", [])
    turning_point = highlights.get("turning_point", {})
    dramatic_tension = highlights.get("dramatic_tension", "")

    # レポート構造を生成
    lines = [
        "# 統合シミュレーションレポート",
        "",
        render_decision_brief_markdown(decision_brief),
        "",
        "---",
        "",
    ]

    # エグゼクティブサマリー
    recommendation = decision_brief.get("recommendation", "")
    summary = decision_brief.get("decision_summary", "")
    why_now = decision_brief.get("why_now", "")
    lines.extend([
        "## エグゼクティブサマリー",
        "",
        f"{summary}" if summary else "",
        "",
        f"**判断: {recommendation}**（合意度: {agreement_score*100:.0f}%）",
        "",
        f"{why_now}" if why_now else "",
        "",
        "---",
        "",
    ])

    # 社会の声
    lines.extend([
        "## 社会の声",
        "",
        f"合計{aggregation.get('total_respondents', 0)}人のエージェントに意見を聴取しました。"
        f"スタンス分布は {dist_text} となり、平均信頼度は{_safe_float(aggregation.get('average_confidence'))*100:.0f}%でした。",
        "",
    ])

    top_concerns = aggregation.get("top_concerns", [])
    if top_concerns:
        lines.append("主な懸念として以下が挙がりました:")
        for c in top_concerns[:5]:
            lines.append(f"- {c}")
        lines.append("")

    # 議論のストーリー
    lines.extend([
        "---",
        "",
        "## 議論のストーリー",
        "",
    ])

    if dramatic_tension:
        lines.extend([dramatic_tension, ""])

    if turning_point:
        tp = turning_point
        lines.extend([
            f"### 転機",
            f"ラウンド{tp.get('round', '?')}で、{tp.get('participant', '参加者')}が{tp.get('moment', '')}。"
            f"{tp.get('impact', '')}",
            "",
        ])

    strongest = highlights.get("strongest_exchange", {})
    if strongest and strongest.get("summary"):
        lines.extend([
            "### 最も白熱した議論",
            f"**論点: {strongest.get('topic', '')}**",
            "",
            strongest.get("summary", ""),
            "",
        ])

    # エージェントの声（引用）
    if key_quotes:
        lines.extend([
            "---",
            "",
            "## エージェントの声",
            "",
        ])
        for q in key_quotes[:5]:
            lines.extend([
                f"> 「{q.get('quote', '')}」",
                f"> — {q.get('speaker', '参加者')}（ラウンド{q.get('round', '?')}）",
                "",
            ])

    # 信念変化の物語
    if belief_journeys:
        lines.extend([
            "---",
            "",
            "## 信念の変化",
            "",
        ])
        for bj in belief_journeys[:3]:
            lines.extend([
                f"### {bj.get('participant', '参加者')}",
                f"当初: {bj.get('start', '?')} → 最終: {bj.get('end', '?')}",
                "",
                bj.get("story", ""),
                "",
            ])

    # 合意と対立
    lines.extend([
        "---",
        "",
        "## 合意と対立",
        "",
    ])

    if consensus:
        lines.append("### 合意に至った点")
        for point in consensus:
            lines.append(f"- {point}")
        lines.append("")

    if disagreements:
        lines.append("### 残された対立")
        for d in disagreements:
            if isinstance(d, dict):
                lines.append(f"- **{d.get('topic', '')}**: {', '.join(p.get('position', '') for p in d.get('positions', []))}")
            else:
                lines.append(f"- {d}")
        lines.append("")

    # リスクと提言
    risks = decision_brief.get("risk_factors", [])
    if risks:
        lines.extend(["## リスクファクター", ""])
        for r in risks:
            lines.append(f"- **{r.get('condition', '')}**: {r.get('impact', '')}")
        lines.append("")

    # 時間軸予測
    time_horizon = decision_brief.get("time_horizon", {})
    if time_horizon:
        lines.extend(["## 時間軸予測", ""])
        for period_key in ("short_term", "mid_term", "long_term"):
            period = time_horizon.get(period_key, {})
            if period:
                lines.append(f"- **{period.get('period', '')}**: {period.get('prediction', '')}")
        lines.append("")

    # 次のステップ
    next_steps = decision_brief.get("next_steps", [])
    if next_steps:
        lines.extend(["## 次の検証ステップ", ""])
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
    kg_entities: list[dict] | None = None,
    kg_relations: list[dict] | None = None,
    use_react: bool = True,
) -> SynthesisResult:
    """Synthesis フェーズを実行する。

    Decision Brief 生成 + クロスバリデーション + フルレポート Markdown 生成。
    use_react=True の場合は ReACT パターンで段階的調査型レポートを生成。
    """
    simulation_id = sim.id

    # Decision Brief 生成
    if use_react:
        logger.info("Using ReACT reporter for Decision Brief generation")
        decision_brief, brief_usage = await react_generate_decision_brief(
            theme=theme,
            aggregation=pulse.aggregation,
            evaluation=pulse.evaluation,
            council_synthesis=council.synthesis,
            devil_advocate_summary=council.devil_advocate_summary,
            council_participants=council.participants,
            kg_entities=kg_entities,
            kg_relations=kg_relations,
            council_rounds=council.rounds,
        )
    else:
        decision_brief, brief_usage = await _generate_decision_brief(pulse, council, theme)

    # 合意度計算
    society_summary = {
        "aggregation": pulse.aggregation,
        "evaluation": pulse.evaluation,
    }
    agreement_score = compute_agreement_score(society_summary, council.synthesis)

    # decision_brief に合意度を上書き（計算値を優先）
    decision_brief["agreement_score"] = agreement_score

    # フルレポート Markdown 生成（ナラティブ形式）
    content = await _build_narrative_report(
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
            "population_count": pulse.population_count,
            "selected_count": len(pulse.agents),
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
