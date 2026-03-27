"""ReACT Report Agent: 段階的調査型 Decision Brief 生成

MiroFish の ReACT パターンに着想を得た6段階のレポート生成:
1. Insight Mining: 社会パルスデータのパターン分析
2. Evidence Search: KG から支持/反証エビデンスを検索（反復型）
3. Stakeholder Interview: 反証役の論点と評議会討論の統合
4. Agent Interview: 会議参加者から直接引用を取得
5. Cross-Validation: 社会パルス vs 評議会結論の整合性チェック
6. Report Composition: 全証拠を使って Decision Brief を生成
"""

import logging

from src.app.llm.multi_client import multi_llm_client

logger = logging.getLogger(__name__)


async def react_generate_decision_brief(
    theme: str,
    aggregation: dict,
    evaluation: dict,
    council_synthesis: dict,
    devil_advocate_summary: str,
    council_participants: list[dict],
    kg_entities: list[dict] | None = None,
    kg_relations: list[dict] | None = None,
    council_rounds: list[list[dict]] | None = None,
) -> tuple[dict, dict]:
    """ReACT パターンで Decision Brief を生成する。

    Returns:
        (decision_brief_dict, usage_dict)
    """
    multi_llm_client.initialize()
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # === Step 1: Insight Mining ===
    insights, usage1 = await _step_insight_mining(theme, aggregation, evaluation)
    _add_usage(total_usage, usage1)

    # === Step 2: Evidence Search (Iterative) ===
    evidence, usage2 = await _step_evidence_search(
        theme, insights, kg_entities or [], kg_relations or [],
    )
    _add_usage(total_usage, usage2)

    # === Step 3: Stakeholder Interview ===
    stakeholder_analysis, usage3 = await _step_stakeholder_interview(
        theme, council_synthesis, devil_advocate_summary, council_participants,
    )
    _add_usage(total_usage, usage3)

    # === Step 4: Agent Interview (New) ===
    agent_quotes, usage4 = await _step_agent_interview(
        theme, council_rounds or [], council_participants,
    )
    _add_usage(total_usage, usage4)

    # === Step 5: Cross-Validation (New) ===
    cross_validation, usage5 = await _step_cross_validate(
        theme, aggregation, council_synthesis, insights,
    )
    _add_usage(total_usage, usage5)

    # === Step 6: Report Composition ===
    brief, usage6 = await _step_compose_brief(
        theme, insights, evidence, stakeholder_analysis, aggregation,
        agent_quotes=agent_quotes,
        cross_validation=cross_validation,
    )
    _add_usage(total_usage, usage6)

    return brief, total_usage


async def _step_insight_mining(
    theme: str, aggregation: dict, evaluation: dict,
) -> tuple[dict, dict]:
    """Step 1: 社会パルスデータからパターンを分析する。"""
    system_prompt = (
        "あなたは社会調査データのアナリストです。\n"
        "以下のデータからキーインサイトを3-5個抽出してください。\n\n"
        "出力はJSON形式のみで:\n"
        '{"insights": [{"finding": "発見", "significance": "意義", "confidence": 0.0-1.0}],'
        ' "dominant_narrative": "支配的なナラティブ",'
        ' "tension_points": ["緊張点1", "緊張点2"]}'
    )

    stance_dist = aggregation.get("stance_distribution", {})
    concerns = aggregation.get("top_concerns", [])
    priorities = aggregation.get("top_priorities", [])
    avg_conf = aggregation.get("average_confidence", 0)
    total = aggregation.get("total_respondents", 0)
    failed = aggregation.get("failed_count", 0)

    user_prompt = (
        f"テーマ: {theme}\n\n"
        f"社会調査データ:\n"
        f"- 回答者数: {total}人（失敗: {failed}件）\n"
        f"- スタンス分布: {stance_dist}\n"
        f"- 平均信頼度: {avg_conf}\n"
        f"- 主な懸念: {concerns}\n"
        f"- 主な優先事項: {priorities}\n"
        f"- 評価メトリクス: {evaluation}\n"
    )

    try:
        result, usage = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=2048,
        )
        if isinstance(result, dict):
            return result, usage
    except Exception as e:
        logger.warning("Insight mining failed: %s", e)

    return {
        "insights": [{"finding": f"スタンス分布: {stance_dist}", "significance": "基礎データ", "confidence": avg_conf}],
        "dominant_narrative": "データ分析中",
        "tension_points": concerns[:3],
    }, {}


async def _step_evidence_search(
    theme: str, insights: dict,
    kg_entities: list[dict], kg_relations: list[dict],
) -> tuple[dict, dict]:
    """Step 2: KG からエビデンスを検索する（反復型: 最低3件のエビデンスを確保）。"""
    if not kg_entities:
        return {"supporting_evidence": [], "contradicting_evidence": [], "gaps": ["KGデータなし"]}, {}

    total_usage: dict = {}
    tension_points = insights.get("tension_points", [])

    for attempt in range(2):  # 最大2回試行
        # 重要エンティティを抽出（2回目は範囲を拡大）
        limit = 10 if attempt == 0 else 20
        top_entities = sorted(
            kg_entities, key=lambda e: e.get("importance_score", 0), reverse=True,
        )[:limit]

        entity_summaries = "\n".join(
            f"- {e.get('name', '')}: {e.get('description', '')} (重要度: {e.get('importance_score', 0):.2f})"
            for e in top_entities
        )

        relation_limit = 15 if attempt == 0 else 30
        relation_summaries = "\n".join(
            f"- {r.get('source', '')} --[{r.get('type', '')}]--> {r.get('target', '')} ({r.get('evidence', '')[:100]})"
            for r in kg_relations[:relation_limit]
        )

        search_focus = ""
        if attempt > 0:
            search_focus = (
                "\n\n【重要】前回の検索ではエビデンスが不足していました。"
                "より広い範囲で、間接的な関連も含めてエビデンスを探してください。"
                "各インサイトに対して最低1件のエビデンスを見つけてください。"
            )

        system_prompt = (
            "あなたはエビデンス検索の専門家です。\n"
            "ナレッジグラフのエンティティ・関係から、インサイトを支持/反証するエビデンスを検索してください。\n"
            "最低3件のエビデンス（支持+反証の合計）を見つけてください。\n\n"
            "出力はJSON形式のみで:\n"
            '{"supporting_evidence": [{"entity": "名前", "evidence": "具体的な内容を200文字以上で", "relevance": 0.0-1.0}],'
            ' "contradicting_evidence": [{"entity": "名前", "evidence": "具体的な内容を200文字以上で", "relevance": 0.0-1.0}],'
            ' "gaps": ["検証できないこと1"]}'
            f"{search_focus}"
        )

        user_prompt = (
            f"テーマ: {theme}\n\n"
            f"インサイト: {insights.get('dominant_narrative', '')}\n"
            f"緊張点: {tension_points}\n\n"
            f"KGエンティティ:\n{entity_summaries}\n\n"
            f"KG関係:\n{relation_summaries}\n"
        )

        try:
            result, usage = await multi_llm_client.call(
                provider_name="openai",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=3072,
            )
            total_usage = usage
            if isinstance(result, dict):
                supporting = result.get("supporting_evidence", [])
                contradicting = result.get("contradicting_evidence", [])
                total_evidence = len(supporting) + len(contradicting)
                if total_evidence >= 3 or attempt == 1:
                    logger.info("Evidence search: %d supporting, %d contradicting (attempt %d)",
                                len(supporting), len(contradicting), attempt + 1)
                    return result, total_usage
                logger.info("Evidence search: only %d items found, retrying with broader scope", total_evidence)
        except Exception as e:
            logger.warning("Evidence search attempt %d failed: %s", attempt + 1, e)

    return {"supporting_evidence": [], "contradicting_evidence": [], "gaps": ["検索失敗"]}, total_usage


async def _step_stakeholder_interview(
    theme: str, council_synthesis: dict,
    devil_advocate_summary: str, participants: list[dict],
) -> tuple[dict, dict]:
    """Step 3: 評議会データからステークホルダー分析を生成する。"""
    consensus = council_synthesis.get("consensus_points", []) or []
    disagreements = council_synthesis.get("disagreement_points", []) or []
    recommendations = council_synthesis.get("recommendations", []) or []
    stance_shifts = council_synthesis.get("stance_shifts", []) or []
    most_persuasive = council_synthesis.get("most_persuasive_argument", {})

    participant_summaries = "\n".join(
        f"- {p.get('display_name', '?')} ({p.get('role', '')}): "
        f"{'反証役' if p.get('is_devil_advocate') else ''} "
        f"スタンス={p.get('stance', '?')}"
        for p in participants
    )

    system_prompt = (
        "あなたはステークホルダー分析の専門家です。\n"
        "評議会の議論結果を分析し、主要ステークホルダーの反応予測を生成してください。\n\n"
        "出力はJSON形式のみで:\n"
        '{"key_agreements": ["合意点"],'
        ' "key_disagreements": ["対立点"],'
        ' "persuasion_dynamics": "議論中の説得力学",'
        ' "devil_advocate_strength": "反証の強さ（weak/moderate/strong）",'
        ' "stakeholder_predictions": [{"group": "グループ", "reaction": "反応", "risk_level": "low/medium/high"}],'
        ' "implementation_risks": ["実装リスク"]}'
    )

    user_prompt = (
        f"テーマ: {theme}\n\n"
        f"参加者:\n{participant_summaries}\n\n"
        f"合意点: {consensus}\n"
        f"対立点: {disagreements}\n"
        f"スタンス変化: {stance_shifts}\n"
        f"最も説得力があった主張: {most_persuasive}\n"
        f"反証役サマリー: {devil_advocate_summary}\n"
        f"提言: {recommendations}\n"
    )

    try:
        result, usage = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=2048,
        )
        if isinstance(result, dict):
            return result, usage
    except Exception as e:
        logger.warning("Stakeholder interview failed: %s", e)

    return {
        "key_agreements": consensus[:3],
        "key_disagreements": [str(d) for d in disagreements[:3]],
        "persuasion_dynamics": "分析失敗",
        "devil_advocate_strength": "unknown",
        "stakeholder_predictions": [],
        "implementation_risks": [],
    }, {}


async def _step_agent_interview(
    theme: str,
    council_rounds: list[list[dict]],
    council_participants: list[dict],
) -> tuple[dict, dict]:
    """Step 4: 会議参加者から直接引用を取得する。"""
    if not council_rounds:
        return {"quotes": [], "belief_stories": []}, {}

    # 最もインパクトのある発言を5件抽出
    all_args = []
    for round_args in council_rounds:
        for arg in round_args:
            argument = arg.get("argument", "")
            if argument and len(argument) > 50:
                all_args.append(arg)

    if not all_args:
        return {"quotes": [], "belief_stories": []}, {}

    # 信念変化があった参加者を特定
    belief_changers = [
        a for a in all_args
        if a.get("belief_update") and a.get("belief_update", "").strip()
    ]

    # 発言サマリーを構築
    arg_text = "\n".join(
        f"- [{a.get('participant_name', '?')} (R{a.get('round', '?')})] {(a.get('argument', '') or '')[:300]}"
        for a in all_args[:15]
    )
    belief_text = "\n".join(
        f"- {a.get('participant_name', '?')}: {a.get('belief_update', '')}"
        for a in belief_changers[:5]
    ) if belief_changers else "信念変化なし"

    system_prompt = (
        "あなたはジャーナリストです。議論の参加者の発言から、レポートに引用できる印象的な発言と、\n"
        "信念が変わった参加者のストーリーを抽出してください。\n\n"
        "出力はJSON形式のみで:\n"
        "{\n"
        '  "quotes": [{"speaker": "名前", "quote": "引用（原文を尊重しつつ100-200文字に編集）", "context": "どの場面での発言か"}],\n'
        '  "belief_stories": [{"participant": "名前", "before": "当初の立場", "after": "最終的な立場", "turning_point": "何が転機になったか", "narrative": "100-200文字のストーリー"}]\n'
        "}"
    )

    user_prompt = (
        f"テーマ: {theme}\n\n"
        f"議論からの発言:\n{arg_text}\n\n"
        f"信念変化:\n{belief_text}\n"
    )

    try:
        result, usage = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=2048,
        )
        if isinstance(result, dict):
            return result, usage
    except Exception as e:
        logger.warning("Agent interview failed: %s", e)

    return {"quotes": [], "belief_stories": []}, {}


async def _step_cross_validate(
    theme: str,
    aggregation: dict,
    council_synthesis: dict,
    insights: dict,
) -> tuple[dict, dict]:
    """Step 5: 社会パルス vs 評議会結論の整合性をチェックする。"""
    stance_dist = aggregation.get("stance_distribution", {})
    avg_conf = aggregation.get("average_confidence", 0)
    consensus = council_synthesis.get("consensus_points", []) or []
    disagreements = council_synthesis.get("disagreement_points", []) or []
    recommendations = council_synthesis.get("recommendations", []) or []
    dominant_narrative = insights.get("dominant_narrative", "")

    system_prompt = (
        "あなたはデータ検証の専門家です。\n"
        "大規模社会調査の結果と少人数評議会の結論を比較し、整合性を検証してください。\n"
        "乖離がある場合は、なぜ乖離しているかの仮説を立ててください。\n\n"
        "出力はJSON形式のみで:\n"
        "{\n"
        '  "alignment_score": 0.0-1.0,\n'
        '  "consistent_findings": ["一致している点"],\n'
        '  "divergences": [{"finding": "乖離点", "society_says": "社会調査の結果", "council_says": "評議会の結論", "hypothesis": "乖離の仮説"}],\n'
        '  "reliability_notes": ["信頼性に関する注意点"],\n'
        '  "recommendation_validity": "評議会の提言は社会調査結果とどの程度整合しているか"\n'
        "}"
    )

    user_prompt = (
        f"テーマ: {theme}\n\n"
        f"=== 社会調査（大規模） ===\n"
        f"スタンス分布: {stance_dist}\n"
        f"平均信頼度: {avg_conf}\n"
        f"支配的ナラティブ: {dominant_narrative}\n\n"
        f"=== 評議会（少人数） ===\n"
        f"合意点: {consensus}\n"
        f"対立点: {disagreements}\n"
        f"提言: {recommendations}\n"
    )

    try:
        result, usage = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=2048,
        )
        if isinstance(result, dict):
            return result, usage
    except Exception as e:
        logger.warning("Cross-validation failed: %s", e)

    return {
        "alignment_score": 0.5,
        "consistent_findings": [],
        "divergences": [],
        "reliability_notes": ["クロスバリデーション未実施"],
        "recommendation_validity": "検証不可",
    }, {}


async def _step_compose_brief(
    theme: str, insights: dict, evidence: dict,
    stakeholder_analysis: dict, aggregation: dict,
    agent_quotes: dict | None = None,
    cross_validation: dict | None = None,
) -> tuple[dict, dict]:
    """Step 6: 全データを統合して Decision Brief を生成する。"""
    system_prompt = (
        "あなたは戦略コンサルタントです。\n"
        "4段階の調査結果を統合し、意思決定者向けの Decision Brief をJSON形式で作成してください。\n\n"
        "各セクションにはこれまでの調査で得た具体的なエビデンスを引用してください。\n"
        "抽象的な一般論は禁止。テーマ固有の具体的な洞察を記述してください。\n\n"
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

    # インサイトを構造化
    insight_text = "\n".join(
        f"- {i.get('finding', '')}（信頼度: {i.get('confidence', 0):.0%}）"
        for i in insights.get("insights", [])
    )

    # エビデンスを構造化
    supporting = evidence.get("supporting_evidence", [])
    contradicting = evidence.get("contradicting_evidence", [])
    gaps = evidence.get("gaps", [])

    evidence_text = "支持エビデンス:\n" + "\n".join(
        f"- {e.get('entity', '')}: {e.get('evidence', '')}" for e in supporting
    ) if supporting else "支持エビデンス: なし"

    evidence_text += "\n\n反証エビデンス:\n" + "\n".join(
        f"- {e.get('entity', '')}: {e.get('evidence', '')}" for e in contradicting
    ) if contradicting else "\n\n反証エビデンス: なし"

    # ステークホルダー分析を構造化
    agreements = stakeholder_analysis.get("key_agreements", [])
    disagreements = stakeholder_analysis.get("key_disagreements", [])
    predictions = stakeholder_analysis.get("stakeholder_predictions", [])
    implementation_risks = stakeholder_analysis.get("implementation_risks", [])

    user_prompt = (
        f"テーマ: {theme}\n\n"
        f"=== Step 1: インサイト ===\n{insight_text}\n"
        f"支配的ナラティブ: {insights.get('dominant_narrative', '')}\n"
        f"緊張点: {insights.get('tension_points', [])}\n\n"
        f"=== Step 2: エビデンス ===\n{evidence_text}\n"
        f"検証ギャップ: {gaps}\n\n"
        f"=== Step 3: ステークホルダー分析 ===\n"
        f"合意点: {agreements}\n"
        f"対立点: {disagreements}\n"
        f"反証の強さ: {stakeholder_analysis.get('devil_advocate_strength', '?')}\n"
        f"説得力学: {stakeholder_analysis.get('persuasion_dynamics', '')}\n"
        f"ステークホルダー予測: {predictions}\n"
        f"実装リスク: {implementation_risks}\n\n"
        f"=== 社会反応データ ===\n"
        f"スタンス分布: {aggregation.get('stance_distribution', {})}\n"
        f"平均信頼度: {aggregation.get('average_confidence', 0)}\n\n"
    )

    # Step 4: エージェント引用
    quotes = (agent_quotes or {}).get("quotes", [])
    belief_stories = (agent_quotes or {}).get("belief_stories", [])
    if quotes:
        user_prompt += "\n\n=== Step 4: 参加者の声 ===\n"
        for q in quotes[:5]:
            user_prompt += f"- {q.get('speaker', '?')}: 「{q.get('quote', '')}」\n"
    if belief_stories:
        user_prompt += "\n信念変化ストーリー:\n"
        for bs in belief_stories[:3]:
            user_prompt += f"- {bs.get('participant', '?')}: {bs.get('narrative', '')}\n"

    # Step 5: クロスバリデーション
    cv = cross_validation or {}
    if cv.get("divergences"):
        user_prompt += f"\n\n=== Step 5: クロスバリデーション ===\n"
        user_prompt += f"整合性スコア: {cv.get('alignment_score', '?')}\n"
        for d in cv.get("divergences", [])[:3]:
            user_prompt += f"- 乖離: {d.get('finding', '')} → 仮説: {d.get('hypothesis', '')}\n"
        user_prompt += f"提言の妥当性: {cv.get('recommendation_validity', '')}\n"

    user_prompt += (
        "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "上記の全調査結果を統合し、エビデンスに基づいた Decision Brief を作成してください。\n\n"
        "【重要】\n"
        "- 各 key_reason には必ず具体的な引用元（社会パルスのデータ、評議会の誰の発言、KGのどのエンティティ）を evidence に記載すること\n"
        "- 「一般的に〜」「通常〜」のような根拠のない記述は禁止\n"
        "- 参加者の声セクションがある場合は、stakeholder_reactions に実際の引用を反映すること"
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

        logger.warning("ReACT compose returned non-dict: %.100s", str(result)[:100])
    except Exception as e:
        logger.error("ReACT compose failed: %s", e)

    # フォールバック（最低限のデータから構成）
    return {
        "recommendation": "条件付きGo",
        "decision_summary": insights.get("dominant_narrative", "調査中"),
        "evidence_gaps": gaps,
        "next_steps": [a for a in agreements[:2]] if agreements else ["追加調査が必要"],
    }, {}


def _add_usage(total: dict, usage: dict) -> None:
    """usage を total に加算する。"""
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        total[key] = total.get(key, 0) + usage.get(key, 0)
