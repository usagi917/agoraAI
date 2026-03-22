"""構造化ナラティブレポート生成:
Meeting の synthesis + activation responses + demographic analysis から
エージェント引用付きの構造化JSONナラティブを生成する。
"""

import logging
from collections import Counter

logger = logging.getLogger(__name__)


def _extract_agent_quotes(
    agents: list[dict],
    responses: list[dict],
    stance_filter: str | None = None,
    limit: int = 3,
) -> list[dict]:
    """エージェント引用を抽出する。"""
    quotes = []
    for agent, resp in zip(agents, responses):
        if stance_filter and resp.get("stance") != stance_filter:
            continue
        reason = resp.get("reason", "")
        if not reason:
            continue
        demo = agent.get("demographics", {})
        quotes.append({
            "agent_id": agent.get("id", ""),
            "agent_index": agent.get("agent_index", 0),
            "occupation": demo.get("occupation", ""),
            "age": demo.get("age", 0),
            "region": demo.get("region", ""),
            "stance": resp.get("stance", ""),
            "confidence": resp.get("confidence", 0),
            "quote": reason[:200],
        })
    # confidence の高い順にソート
    quotes.sort(key=lambda q: q["confidence"], reverse=True)
    return quotes[:limit]


def _build_consensus_areas(
    synthesis: dict,
    agents: list[dict],
    responses: list[dict],
) -> list[dict]:
    """合意点をエージェント引用付きで構築する。"""
    consensus_points = synthesis.get("consensus_points", [])
    if not consensus_points:
        return []

    # 合意に賛同しているエージェント（賛成 or 条件付き賛成）
    supporting_quotes = _extract_agent_quotes(agents, responses, stance_filter=None, limit=5)

    return [
        {
            "point": point,
            "supporting_agents": supporting_quotes[:2],
        }
        for point in consensus_points
    ]


def _build_controversy_areas(
    synthesis: dict,
    agents: list[dict],
    responses: list[dict],
    demographic_analysis: dict,
) -> list[dict]:
    """対立点をデモグラフィック分割付きで構築する。"""
    disagreement_points = synthesis.get("disagreement_points", [])
    if not disagreement_points:
        return []

    # スタンス別引用
    pro_quotes = _extract_agent_quotes(agents, responses, stance_filter="賛成", limit=2)
    con_quotes = _extract_agent_quotes(agents, responses, stance_filter="反対", limit=2)

    # デモグラフィック分割: 最も分かれている属性を見つける
    age_data = demographic_analysis.get("by_age", {})
    region_data = demographic_analysis.get("by_region", {})

    controversies = []
    for dp in disagreement_points:
        topic = dp.get("topic", "") if isinstance(dp, dict) else str(dp)
        positions = dp.get("positions", []) if isinstance(dp, dict) else []

        controversies.append({
            "point": topic,
            "positions": positions,
            "supporting_quotes": pro_quotes[:1],
            "opposing_quotes": con_quotes[:1],
            "demographic_split": {
                "by_age": {
                    k: v.get("distribution", {})
                    for k, v in list(age_data.items())[:3]
                },
                "by_region": {
                    k: v.get("distribution", {})
                    for k, v in list(region_data.items())[:3]
                },
            },
        })

    return controversies


def _build_recommendations(
    synthesis: dict,
    agents: list[dict],
    responses: list[dict],
    meeting_rounds: list[list[dict]],
) -> list[dict]:
    """提言をエビデンスチェーン付きで構築する。"""
    recommendations = synthesis.get("recommendations", [])
    if not recommendations:
        return []

    # Meeting から根拠となる発言を抽出
    evidence_pool = []
    for round_args in meeting_rounds:
        for arg in round_args:
            if arg.get("evidence"):
                evidence_pool.append({
                    "participant_name": arg.get("participant_name", ""),
                    "role": arg.get("role", ""),
                    "round": arg.get("round", 0),
                    "evidence": arg["evidence"],
                    "argument": arg.get("argument", ""),
                })

    return [
        {
            "recommendation": rec,
            "evidence_chain": evidence_pool[:2],
            "supporting_agents": _extract_agent_quotes(agents, responses, limit=2),
        }
        for rec in recommendations
    ]


def _build_executive_summary(
    synthesis: dict,
    aggregation: dict,
    demographic_analysis: dict,
) -> str:
    """エグゼクティブサマリーを構築する。"""
    overall = synthesis.get("overall_assessment", "")
    if overall:
        return overall

    # fallback: aggregation から生成
    dist = aggregation.get("stance_distribution", {})
    total = aggregation.get("total_respondents", 0)
    avg_conf = aggregation.get("average_confidence", 0)

    if not dist:
        return ""

    top_stance = max(dist, key=dist.get) if dist else "不明"
    top_ratio = dist.get(top_stance, 0)

    return (
        f"{total}人の市民を対象とした活性化調査の結果、"
        f"最多スタンスは「{top_stance}」({top_ratio * 100:.0f}%)、"
        f"平均信頼度は{avg_conf * 100:.0f}%でした。"
    )


def _build_key_findings(
    synthesis: dict,
    agents: list[dict],
    responses: list[dict],
) -> list[dict]:
    """主要発見事項を構築する。"""
    key_insights = synthesis.get("key_insights", [])
    scenarios = synthesis.get("scenarios", [])

    findings = []

    for insight in key_insights:
        findings.append({
            "finding": insight,
            "type": "insight",
            "supporting_evidence": _extract_agent_quotes(agents, responses, limit=2),
            "confidence": 0.7,
        })

    for scenario in scenarios:
        if isinstance(scenario, dict):
            findings.append({
                "finding": scenario.get("description", scenario.get("name", "")),
                "type": "scenario",
                "probability": scenario.get("probability", 0),
                "key_factors": scenario.get("key_factors", []),
                "confidence": scenario.get("probability", 0.5),
            })

    return findings


def generate_narrative(
    agents: list[dict],
    responses: list[dict],
    synthesis: dict,
    aggregation: dict,
    demographic_analysis: dict,
    meeting_rounds: list[list[dict]] | None = None,
) -> dict:
    """構造化ナラティブレポートを生成する。

    Returns:
        {
            "executive_summary": str,
            "key_findings": [...],
            "consensus_areas": [...],
            "controversy_areas": [...],
            "recommendations": [...],
            "stance_shifts": [...],
        }
    """
    if not synthesis:
        synthesis = {}
    if not meeting_rounds:
        meeting_rounds = []

    narrative = {
        "executive_summary": _build_executive_summary(
            synthesis, aggregation, demographic_analysis,
        ),
        "key_findings": _build_key_findings(
            synthesis, agents, responses,
        ),
        "consensus_areas": _build_consensus_areas(
            synthesis, agents, responses,
        ),
        "controversy_areas": _build_controversy_areas(
            synthesis, agents, responses, demographic_analysis,
        ),
        "recommendations": _build_recommendations(
            synthesis, agents, responses, meeting_rounds,
        ),
        "stance_shifts": synthesis.get("stance_shifts", []),
    }

    logger.info(
        "Narrative generated: %d findings, %d consensus, %d controversies, %d recommendations",
        len(narrative["key_findings"]),
        len(narrative["consensus_areas"]),
        len(narrative["controversy_areas"]),
        len(narrative["recommendations"]),
    )

    return narrative
