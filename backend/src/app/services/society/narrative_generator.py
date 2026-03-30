"""構造化ナラティブレポート生成:
Meeting の synthesis + activation responses + demographic analysis から
エージェント引用付きの構造化JSONナラティブを生成する。
"""

import logging

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


def _build_controversy_areas_v2(
    synthesis: dict,
    agents: list[dict],
    responses: list[dict],
    demographic_analysis: dict,
    clusters: list[dict] | None = None,
) -> list[dict]:
    """対立点をクラスタ・確信度・ブリッジエージェント付きで構築する（v2）。

    Each controversy includes:
    - point: 対立軸のラベル
    - supporting_stances: この対立に関連するスタンスのリスト
    - cluster_analysis: クラスタ情報（提供された場合）
    - conviction_strength: 各側の平均確信度
    - bridge_agents: クラスタ境界付近のエージェント
    - demographic_split: デモグラフィック分割
    """
    disagreement_points = synthesis.get("disagreement_points", [])
    if not disagreement_points:
        return []

    # Build response lookup
    response_map: dict[str, dict] = {}
    agent_map: dict[str, dict] = {}
    for agent, resp in zip(agents, responses):
        aid = agent.get("id", "")
        response_map[aid] = resp
        agent_map[aid] = agent

    # Cluster membership lookup
    cluster_membership: dict[str, int] = {}
    if clusters:
        for cluster in clusters:
            for mid in cluster.get("member_ids", []):
                cluster_membership[mid] = cluster.get("label", -1)

    # Stance-grouped agents
    pro_agents = [
        (a, r) for a, r in zip(agents, responses)
        if r.get("stance") in ("賛成", "条件付き賛成")
    ]
    con_agents = [
        (a, r) for a, r in zip(agents, responses)
        if r.get("stance") in ("反対", "条件付き反対")
    ]

    # Conviction strength
    pro_confidence = (
        sum(r.get("confidence", 0) for _, r in pro_agents) / len(pro_agents)
        if pro_agents else 0.0
    )
    con_confidence = (
        sum(r.get("confidence", 0) for _, r in con_agents) / len(con_agents)
        if con_agents else 0.0
    )

    # Bridge agents: those with opinion_vector near 0.5 (center)
    bridge_agents = []
    if clusters and len(clusters) >= 2:
        for agent, resp in zip(agents, responses):
            op = resp.get("opinion_vector", [0.5])
            if op and 0.35 <= op[0] <= 0.65:
                demo = agent.get("demographics", {})
                bridge_agents.append({
                    "agent_id": agent.get("id", ""),
                    "agent_index": agent.get("agent_index", 0),
                    "stance": resp.get("stance", ""),
                    "opinion_value": round(op[0], 3),
                    "occupation": demo.get("occupation", ""),
                    "region": demo.get("region", ""),
                })
    bridge_agents.sort(key=lambda x: abs(x.get("opinion_value", 0.5) - 0.5))
    bridge_agents = bridge_agents[:5]

    # Demographic splits
    age_data = demographic_analysis.get("by_age", {})
    region_data = demographic_analysis.get("by_region", {})

    controversies = []
    for dp in disagreement_points:
        topic = dp.get("topic", "") if isinstance(dp, dict) else str(dp)
        positions = dp.get("positions", []) if isinstance(dp, dict) else []

        # Stances involved
        supporting_stances = []
        for pos in positions:
            supporting_stances.append(pos)

        # Cluster analysis
        cluster_analysis = {}
        if clusters and len(clusters) >= 2:
            cluster_analysis = {
                "cluster_count": len(clusters),
                "clusters": [
                    {
                        "label": c.get("label"),
                        "size": c.get("size"),
                        "centroid": c.get("centroid"),
                    }
                    for c in clusters
                ],
            }

        # Pro/con quotes
        pro_quotes = _extract_agent_quotes(agents, responses, stance_filter="賛成", limit=2)
        con_quotes = _extract_agent_quotes(agents, responses, stance_filter="反対", limit=2)

        controversies.append({
            "point": topic,
            "positions": positions,
            "supporting_stances": supporting_stances,
            "supporting_quotes": pro_quotes[:1],
            "opposing_quotes": con_quotes[:1],
            "conviction_strength": {
                "pro_average_confidence": round(pro_confidence, 3),
                "con_average_confidence": round(con_confidence, 3),
            },
            "cluster_analysis": cluster_analysis,
            "bridge_agents": bridge_agents,
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


def _build_methodology_section(provenance: dict) -> str:
    """provenance dict からマークダウン形式のメソドロジーセクションを生成する。"""
    lines: list[str] = ["## 方法論"]

    # --- 標本設計 ---
    params = provenance.get("parameters", {})
    population_size = params.get("population_size", "不明")
    selected_sample_size = params.get("selected_sample_size", "不明")
    effective_sample_size = params.get("effective_sample_size", "不明")

    lines.append("")
    lines.append("### 標本設計")
    lines.append(f"- 母集団規模: {population_size:,}人" if isinstance(population_size, (int, float)) else f"- 母集団規模: {population_size}")
    lines.append(f"- 選出標本数: {selected_sample_size}人")
    lines.append(f"- 有効標本数 (effective_sample_size): {effective_sample_size}")

    # --- 信頼区間 ---
    lines.append("")
    lines.append("### 信頼区間")
    lines.append(
        "スタンス分布の95%信頼区間はブートストラップ法（リサンプリング回数: 1,000回）により算出しました。"
        "信頼区間はポスト層化重み付けを適用した有効標本数を基に計算されます。"
    )

    # --- 熟議プロトコル ---
    methodology = provenance.get("methodology", {})
    framework = methodology.get("framework", "")
    citation = methodology.get("citation", "")
    deliberation_protocol = methodology.get("deliberation_protocol", "")
    aggregation_method = methodology.get("aggregation_method", "")

    lines.append("")
    lines.append("### 熟議プロトコル")
    if framework:
        lines.append(f"- フレームワーク: {framework}")
    if deliberation_protocol:
        lines.append(f"- 熟議手順: {deliberation_protocol}")
    if aggregation_method:
        lines.append(f"- 集計手法: {aggregation_method}")
    if citation:
        lines.append(f"- 参考文献: {citation}")

    # --- データソース ---
    data_sources = provenance.get("data_sources", [])
    if data_sources:
        lines.append("")
        lines.append("### データソース")
        for source in data_sources:
            name = source.get("name", "")
            used_for = source.get("used_for", "")
            if name and used_for:
                lines.append(f"- {name}（用途: {used_for}）")
            elif name:
                lines.append(f"- {name}")

    # --- 制約事項 ---
    limitations = provenance.get("limitations", [])
    if limitations:
        lines.append("")
        lines.append("### 制約事項と限界")
        for limitation in limitations:
            lines.append(f"- {limitation}")

    return "\n".join(lines)


def generate_narrative(
    agents: list[dict],
    responses: list[dict],
    synthesis: dict,
    aggregation: dict,
    demographic_analysis: dict,
    meeting_rounds: list[list[dict]] | None = None,
    provenance: dict | None = None,
    clusters: list[dict] | None = None,
) -> dict:
    """構造化ナラティブレポートを生成する。

    Args:
        clusters: Network propagation で検出されたクラスタ情報（v2対立分析用）

    Returns:
        {
            "executive_summary": str,
            "key_findings": [...],
            "consensus_areas": [...],
            "controversy_areas": [...],
            "recommendations": [...],
            "stance_shifts": [...],
            "methodology_section": str | None,
        }
    """
    if not synthesis:
        synthesis = {}
    if not meeting_rounds:
        meeting_rounds = []

    # Use v2 controversy builder when cluster data is available
    if clusters:
        controversy_areas = _build_controversy_areas_v2(
            synthesis, agents, responses, demographic_analysis, clusters=clusters,
        )
    else:
        controversy_areas = _build_controversy_areas(
            synthesis, agents, responses, demographic_analysis,
        )

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
        "controversy_areas": controversy_areas,
        "recommendations": _build_recommendations(
            synthesis, agents, responses, meeting_rounds,
        ),
        "stance_shifts": synthesis.get("stance_shifts", []),
        "methodology_section": _build_methodology_section(provenance) if provenance is not None else None,
    }

    logger.info(
        "Narrative generated: %d findings, %d consensus, %d controversies, %d recommendations",
        len(narrative["key_findings"]),
        len(narrative["consensus_areas"]),
        len(narrative["controversy_areas"]),
        len(narrative["recommendations"]),
    )

    return narrative
