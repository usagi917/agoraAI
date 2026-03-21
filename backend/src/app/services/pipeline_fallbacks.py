"""Deterministic fallback builders for PM Board and pipeline reports."""

from __future__ import annotations

import re

from src.app.services.quality import build_quality_summary


def _clean_text(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""

    text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _shorten(value: str | None, limit: int = 900) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _coerce_probability(value) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, probability))


def _extract_scenarios(
    scenario_candidates: list[dict] | None = None,
    context_excerpt: str = "",
) -> list[dict]:
    scenarios: list[dict] = []

    for item in scenario_candidates or []:
        description = str(item.get("description", "")).strip()
        if not description:
            continue
        scenarios.append({
            "description": description,
            "probability": _coerce_probability(item.get("probability")),
            "agreement_ratio": _coerce_probability(item.get("agreement_ratio")),
        })

    if scenarios:
        return scenarios[:5]

    for line in _clean_text(context_excerpt).splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        match = re.match(r"-\s*(.+?)(?:[:：]\s*確率?\s*(\d{1,3})%?)?$", stripped)
        if not match:
            continue
        description = match.group(1).strip()
        if not description:
            continue
        probability = None
        if match.group(2):
            probability = _coerce_probability(int(match.group(2)) / 100)
        scenarios.append({
            "description": description,
            "probability": probability,
            "agreement_ratio": None,
        })

    return scenarios[:5]


def pm_board_has_substance(pm_result: dict | None) -> bool:
    if not isinstance(pm_result, dict):
        return False

    sections = pm_result.get("sections", {})
    if isinstance(sections, dict):
        for value in sections.values():
            if isinstance(value, str) and value.strip():
                return True
            if isinstance(value, list) and value:
                return True
            if isinstance(value, dict) and any(
                isinstance(nested, str) and nested.strip() or nested
                for nested in value.values()
            ):
                return True

    for key in ("contradictions", "key_decision_points", "pm_analyses"):
        value = pm_result.get(key)
        if isinstance(value, list) and value:
            return True

    confidence = pm_result.get("overall_confidence")
    return isinstance(confidence, (int, float)) and confidence > 0


def build_pm_board_fallback(
    prompt_text: str,
    scenario_candidates: list[dict] | None = None,
    context_excerpt: str = "",
    pm_analyses: list[dict] | None = None,
    usage: dict | None = None,
) -> dict:
    scenarios = _extract_scenarios(scenario_candidates, context_excerpt)
    top_scenario = scenarios[0] if scenarios else {
        "description": "主要シナリオの成立条件を見極める",
        "probability": 0.55,
        "agreement_ratio": 0.5,
    }
    second_scenario = scenarios[1] if len(scenarios) > 1 else None

    top_probability = top_scenario.get("probability")
    if top_probability is None:
        top_probability = 0.55

    contradictions = []
    if second_scenario:
        second_probability = second_scenario.get("probability")
        if second_probability is None:
            second_probability = 0.35
        contradictions.append({
            "between": ["高確度シナリオ", "代替シナリオ"],
            "issue": (
                f"最有力仮説は「{top_scenario['description']}」だが、"
                f"「{second_scenario['description']}」も無視できない。"
            ),
            "resolution": "顧客検証と供給/規制の事実確認を追加し、意思決定を分岐条件つきで行う。",
        })

    prompt_summary = prompt_text.strip() or "このテーマに対して、どの仮説を優先して検証すべきか"
    context_summary = _shorten(context_excerpt, 600)

    return {
        "type": "pm_board",
        "sections": {
            "core_question": prompt_summary,
            "assumptions": [
                {
                    "assumption": top_scenario["description"],
                    "confidence": top_probability,
                    "evidence": "Stage 2 の高確度シナリオから抽出",
                    "impact_if_wrong": "優先すべき市場投入シナリオと投資配分がずれる。",
                },
                {
                    "assumption": "主要な不確実性は顧客需要・供給網・規制動向に集約される。",
                    "confidence": 0.5,
                    "evidence": "Stage 1/2 の要約コンテキストを横断して抽出",
                    "impact_if_wrong": "MVP スコープと検証順序が過剰または不足になる。",
                },
            ],
            "uncertainties": [
                {
                    "uncertainty": "顧客採用速度と導入条件のばらつき",
                    "risk_level": "high",
                    "validation_method": "重点顧客インタビューと案件ヒアリングでボトルネックを特定する。",
                },
                {
                    "uncertainty": "供給/規制条件の変化タイミング",
                    "risk_level": "medium",
                    "validation_method": "パートナー確認と公開情報モニタリングを週次で回す。",
                },
            ],
            "risks": [
                {
                    "risk": "前提条件が未検証のまま広いスコープで開発に入る",
                    "probability": 0.62,
                    "mitigation": "高確度シナリオに直結する検証項目から優先順位を付ける。",
                },
                {
                    "risk": "外部環境変化により想定シナリオの優先度が逆転する",
                    "probability": 0.48,
                    "mitigation": "シナリオ別の Go / Hold 条件を先に明文化する。",
                },
            ],
            "winning_hypothesis": {
                "if_true": top_scenario["description"],
                "then_do": "高確度シナリオに沿って MVP と検証導線を絞り込み、初期顧客で再現性を確認する。",
                "to_achieve": "実行可能な市場投入判断と次段階投資の意思決定",
                "confidence": top_probability,
            },
            "customer_validation_plan": {
                "target_segments": ["重点顧客候補", "提携/供給パートナー"],
                "key_questions": [
                    "最有力シナリオが実務上どの条件で成立するか。",
                    "導入阻害要因として最も大きいものは何か。",
                    "今すぐ検証すべき MVP の最小機能は何か。",
                ],
                "success_criteria": "3件以上の定性的検証で優先ユースケースと阻害要因が一致して説明できる状態。",
            },
            "market_view": {
                "market_size": "十分な検証価値がある市場機会",
                "growth_rate": "外部条件しだいで上振れ余地あり",
                "key_players": [
                    {"name": "既存プレイヤー", "position": "顧客基盤や供給網を保有"},
                    {"name": "新規参入候補", "position": "差別化余地はあるが前提検証が必要"},
                ],
            },
            "gtm_hypothesis": {
                "target_customer": "最有力シナリオの影響を強く受ける初期顧客",
                "value_proposition": "高確度シナリオに対する具体的な実行判断を短期間で支援する。",
                "channel": "既存ネットワーク経由の高密度な仮説検証",
                "pricing_model": "初期導入は検証価値に紐づく限定パッケージ",
            },
            "mvp_scope": {
                "in_scope": [
                    "最有力シナリオの成立条件を確かめる最小機能",
                    "顧客/供給/規制の3論点を追える検証ダッシュボード",
                    "Go / Hold を判断するためのレポート出力",
                ],
                "out_of_scope": [
                    "全セグメントを同時にカバーする汎用化",
                    "検証前提が固まっていない自動化の作り込み",
                ],
            },
            "plan_30_60_90": {
                "day_30": {
                    "goals": ["高確度シナリオの前提条件を明文化する"],
                    "actions": [
                        "顧客/パートナーの検証対象を5件以上選定する",
                        "意思決定に必要な評価指標を固定する",
                    ],
                },
                "day_60": {
                    "goals": ["MVP 仮説と導入障壁を検証する"],
                    "actions": [
                        "ヒアリング結果を反映して MVP スコープを再調整する",
                        "代替シナリオへの切替条件を整理する",
                    ],
                },
                "day_90": {
                    "goals": ["Go / Hold の判断材料を揃える"],
                    "actions": [
                        "初期案件の反応を踏まえた実行計画を確定する",
                        "継続投資の条件と見送り条件を経営判断用に整理する",
                    ],
                },
            },
            "top_5_actions": [
                {
                    "action": "高確度シナリオの成立条件を顧客ヒアリングで検証する",
                    "owner": "PM",
                    "deadline": "30日以内",
                    "confidence": top_probability,
                    "evidence": top_scenario["description"],
                },
                {
                    "action": "供給/規制の変動要因をウォッチする運用を作る",
                    "owner": "BizOps",
                    "deadline": "30日以内",
                    "confidence": 0.58,
                    "evidence": "外部条件の変化が意思決定に直結するため",
                },
                {
                    "action": "MVP を最小スコープへ絞り込み、評価指標を固定する",
                    "owner": "Product",
                    "deadline": "45日以内",
                    "confidence": 0.61,
                    "evidence": "未検証の前提が多い段階では検証速度を優先すべきため",
                },
                {
                    "action": "代替シナリオへ切り替える条件を先に定義する",
                    "owner": "PM",
                    "deadline": "45日以内",
                    "confidence": 0.52,
                    "evidence": second_scenario["description"] if second_scenario else "シナリオ間の不確実性に備えるため",
                },
                {
                    "action": "90日後の Go / Hold 判断メモを先に作る",
                    "owner": "Lead",
                    "deadline": "60日以内",
                    "confidence": 0.57,
                    "evidence": context_summary or "Stage 1/2 の要約から判断論点を前倒しで固定するため",
                },
            ],
        },
        "contradictions": contradictions,
        "overall_confidence": top_probability,
        "key_decision_points": [
            "最有力シナリオの前提が顧客と供給側の両方で再現するか。",
            "MVP を絞ったときに初期顧客価値が残るか。",
            "外部条件が変化した場合に Hold へ切り替える閾値を持てているか。",
        ],
        "pm_analyses": pm_analyses or [],
        "synthesis": {
            "fallback": True,
            "note": "LLM 出力が空だったため、保存済みシナリオと要約から補完した。",
            "context_excerpt": context_summary,
        },
        "usage": usage or {},
        "quality": build_quality_summary(
            fallback_used=True,
            evidence_refs=[],
            fallback_reason="pm_board_llm_output_empty",
        ),
    }


def build_pipeline_report_fallback(
    prompt_text: str,
    single_report: str = "",
    swarm_report: str = "",
    scenarios: list[dict] | None = None,
    pm_result: dict | None = None,
) -> str:
    context_excerpt = "\n\n".join(filter(None, [_shorten(single_report, 700), _shorten(swarm_report, 700)]))
    pm_payload = pm_result if pm_board_has_substance(pm_result) else build_pm_board_fallback(
        prompt_text=prompt_text,
        scenario_candidates=scenarios,
        context_excerpt=context_excerpt,
    )
    pm_sections = pm_payload.get("sections", {}) if isinstance(pm_payload, dict) else {}

    scenario_lines = []
    for item in _extract_scenarios(scenarios, swarm_report):
        details = []
        probability = item.get("probability")
        agreement_ratio = item.get("agreement_ratio")
        if probability is not None:
            details.append(f"確率 {probability:.0%}")
        if agreement_ratio is not None:
            details.append(f"合意率 {agreement_ratio:.0%}")
        suffix = f" ({' / '.join(details)})" if details else ""
        scenario_lines.append(f"- {item['description']}{suffix}")
    if not scenario_lines:
        scenario_lines.append("- 主要シナリオは生成済みだが、要約テキストの再構成のみ行った。")

    actions = pm_sections.get("top_5_actions") or []
    action_lines = [
        f"- {item.get('action', '')}".rstrip()
        for item in actions
        if isinstance(item, dict) and str(item.get("action", "")).strip()
    ] or [
        "- 高確度シナリオの前提条件を顧客/市場/供給の3面で検証する。",
        "- MVP スコープを最小化し、Go / Hold 判断に必要な指標を固定する。",
        "- 代替シナリオへの切替条件を明文化する。",
    ]

    executive_points = [
        f"- 元の問い: {prompt_text.strip() or '入力テーマ'}",
        f"- 最有力シナリオ: {scenario_lines[0][2:] if scenario_lines else '主要シナリオの再評価が必要'}",
        f"- PM 観点の判断軸: {pm_sections.get('core_question') or '検証順序と投資判断を分けて考える'}",
    ]

    return "\n".join([
        "# 統合分析レポート",
        "",
        "## エグゼクティブサマリー",
        *executive_points,
        "",
        "## 因果分析の知見（Stage 1）",
        _shorten(single_report, 1400) or "Stage 1 の詳細レポート要約を取得できなかったため、下流成果物から再構成した。",
        "",
        "## シナリオ検証結果（Stage 2）",
        *scenario_lines,
        "",
        _shorten(swarm_report, 1400) or "Stage 2 の統合レポート本文は保持されていないが、主要シナリオと確率分布は保存済み。",
        "",
        "## PM実務評価（Stage 3）",
        f"- 核心質問: {pm_sections.get('core_question') or 'どの前提を先に検証すべきか'}",
        (
            "- 勝利仮説: IF "
            f"{pm_sections.get('winning_hypothesis', {}).get('if_true', '主要前提が成立する')} "
            "THEN "
            f"{pm_sections.get('winning_hypothesis', {}).get('then_do', 'MVP を絞って検証する')} "
            "TO ACHIEVE "
            f"{pm_sections.get('winning_hypothesis', {}).get('to_achieve', '次の投資判断')}"
        ),
        f"- 総合確信度: {float(pm_payload.get('overall_confidence', 0) or 0):.0%}",
        "",
        "## 統合的知見",
        "- Stage 1 は構造理解、Stage 2 はシナリオ差分、Stage 3 は実行判断へ役割分担されている。",
        "- したがって、最有力シナリオの検証を先に進めつつ、代替シナリオへ切り替える条件を併記する構成が妥当。",
        "",
        "## リスクと不確実性",
        "- 外部条件の変化でシナリオ優先度が反転する可能性がある。",
        "- 顧客価値が確認できる前にスコープを広げると、検証速度が落ちる。",
        "- 供給/規制/競合の変化点を定点観測しないと、判断の鮮度が落ちる。",
        "",
        "## 推奨アクション",
        *action_lines,
        "",
        "## 結論",
        "現時点では、最有力シナリオの成立条件を短期で検証し、MVP と投資判断を段階的に進めるのが最も堅い。"
        " LLM の最終出力が空だったため、保存済みの Stage 成果物から本レポートを補完した。",
    ]).strip()
