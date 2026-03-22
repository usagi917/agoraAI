"""Issue mining for society-first simulations.

Turns society activation outputs into ranked market issues that can be
deep-dived through focused issue colonies.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any


ISSUE_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"価格|値段|コスト|費用|負担"), "価格受容性", 0.92),
    (re.compile(r"規制|法規|行政|コンプライアンス|政策"), "規制対応", 0.9),
    (re.compile(r"安全|品質|故障|リスク|事故"), "安全性と品質信頼", 0.89),
    (re.compile(r"信頼|信用|ブランド|透明"), "ブランド信頼", 0.86),
    (re.compile(r"供給|在庫|物流|調達|生産"), "供給制約", 0.84),
    (re.compile(r"導入|運用|習熟|手間|教育"), "導入障壁", 0.82),
    (re.compile(r"需要|購買|顧客|採用|解約"), "需要と採用", 0.88),
    (re.compile(r"口コミ|拡散|評判|SNS|紹介"), "口コミ拡散", 0.8),
    (re.compile(r"雇用|仕事|収入|賃金"), "雇用影響", 0.8),
    (re.compile(r"環境|脱炭素|CO2|排出"), "環境影響", 0.78),
]

INTERVENTION_LIBRARY: list[dict[str, Any]] = [
    {
        "intervention_id": "price_reduction",
        "label": "価格変更",
        "change_summary": "初期費用を引き下げ、価格に敏感な層の採用障壁を下げる",
        "matched_issues": {"価格受容性", "需要と採用", "導入障壁"},
    },
    {
        "intervention_id": "regulatory_alignment",
        "label": "規制対応強化",
        "change_summary": "制度整合性と説明責任を高め、規制・行政起点の反発を下げる",
        "matched_issues": {"規制対応", "ブランド信頼", "安全性と品質信頼"},
    },
    {
        "intervention_id": "message_refinement",
        "label": "訴求変更",
        "change_summary": "価値訴求と信頼訴求を調整し、誤解や不安を減らす",
        "matched_issues": {"ブランド信頼", "口コミ拡散", "需要と採用", "安全性と品質信頼"},
    },
]


def _clean_text(value: str | None, *, limit: int = 120) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _extract_fallback_label(reason: str) -> str:
    text = _clean_text(reason, limit=36)
    if not text:
        return "意見理由"
    if "。" in text:
        text = text.split("。", 1)[0]
    if len(text) <= 4:
        return "意見理由"
    return text


def _match_issue_label(text: str) -> tuple[str, float]:
    lowered = _clean_text(text)
    for pattern, label, impact in ISSUE_PATTERNS:
        if pattern.search(lowered):
            return label, impact
    return _extract_fallback_label(lowered), 0.65


def _shannon_entropy(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if total <= 1 or len(counter) <= 1:
        return 0.0
    entropy = 0.0
    for count in counter.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy / math.log2(len(counter))


def mine_issue_candidates(
    agents: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    *,
    meeting_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build ranked issue candidates from society activation responses."""
    if not responses:
        return []

    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any], float]]] = defaultdict(list)
    for agent, response in zip(agents, responses):
        source_text = " ".join(
            filter(
                None,
                [
                    _clean_text(response.get("concern")),
                    _clean_text(response.get("priority")),
                    _clean_text(response.get("reason")),
                ],
            )
        )
        label, impact_hint = _match_issue_label(source_text)
        grouped[label].append((agent, response, impact_hint))

    total_population = max(len(responses), 1)
    meeting_topics = {
        _clean_text(item.get("topic"), limit=60)
        for item in (meeting_report or {}).get("disagreement_points", []) or []
        if _clean_text(item.get("topic"))
    }

    candidates: list[dict[str, Any]] = []
    for index, (label, items) in enumerate(grouped.items(), start=1):
        stances = Counter(str(resp.get("stance") or "中立") for _, resp, _ in items)
        population_share = len(items) / total_population
        controversy_score = _shannon_entropy(stances)
        market_impact_score = round(
            sum(impact for _, _, impact in items) / max(len(items), 1),
            3,
        )

        regions = {
            str((agent.get("demographics") or {}).get("region") or "").strip()
            for agent, _, _ in items
            if str((agent.get("demographics") or {}).get("region") or "").strip()
        }
        occupations = {
            str((agent.get("demographics") or {}).get("occupation") or "").strip()
            for agent, _, _ in items
            if str((agent.get("demographics") or {}).get("occupation") or "").strip()
        }
        network_spread_score = min(
            1.0,
            round((len(regions) / 6) * 0.45 + (len(occupations) / 8) * 0.55, 3),
        )

        disagreement_bonus = 0.08 if any(label in topic for topic in meeting_topics) else 0.0
        selection_score = min(
            1.0,
            round(
                population_share * 0.4
                + controversy_score * 0.25
                + market_impact_score * 0.25
                + network_spread_score * 0.1
                + disagreement_bonus,
                3,
            ),
        )

        supporting_stances = [
            {"stance": stance, "share": round(count / len(items), 3)}
            for stance, count in stances.most_common()
        ]
        sample_reasons = []
        seen_reasons: set[str] = set()
        for _, response, _ in items:
            reason = _clean_text(response.get("reason"))
            if reason and reason not in seen_reasons:
                sample_reasons.append(reason)
                seen_reasons.add(reason)
            if len(sample_reasons) >= 3:
                break

        candidates.append({
            "issue_id": f"issue-{index}",
            "label": label,
            "description": f"{label} に関する社会反応の集約論点",
            "population_share": round(population_share, 3),
            "controversy_score": round(controversy_score, 3),
            "market_impact_score": market_impact_score,
            "network_spread_score": network_spread_score,
            "selection_score": selection_score,
            "supporting_stances": supporting_stances,
            "sample_reasons": sample_reasons,
        })

    candidates.sort(
        key=lambda item: (
            item["selection_score"],
            item["market_impact_score"],
            item["population_share"],
        ),
        reverse=True,
    )
    return candidates


def select_top_issues(
    issue_candidates: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    return [dict(item) for item in issue_candidates[:limit]]


def build_issue_prompt(
    *,
    theme: str,
    issue: dict[str, Any],
    society_summary: dict[str, Any],
) -> str:
    stance_lines = [
        f"- {entry['stance']}: {entry['share'] * 100:.0f}%"
        for entry in issue.get("supporting_stances", [])
    ]
    reason_lines = [
        f"- {reason}"
        for reason in issue.get("sample_reasons", [])
    ]
    concern_lines = [
        f"- {concern}"
        for concern in society_summary.get("top_concerns", [])[:3]
    ]
    return "\n".join(
        filter(
            None,
            [
                f"テーマ: {theme}",
                f"重点論点: {issue.get('label', '')}",
                issue.get("description", ""),
                "論点の立場分布:",
                "\n".join(stance_lines) if stance_lines else "- 立場分布データなし",
                "代表的な理由:",
                "\n".join(reason_lines) if reason_lines else "- 代表理由なし",
                "社会全体の主要懸念:",
                "\n".join(concern_lines) if concern_lines else "- 主要懸念なし",
                "この論点が市場シナリオ・採用障壁・反発要因にどう影響するかを深掘りしてください。",
            ],
        )
    )


def build_intervention_comparison(
    selected_issues: list[dict[str, Any]],
    issue_colony_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build simple intervention comparisons from selected issues."""
    issue_by_label = {issue.get("label"): issue for issue in selected_issues}
    issue_result_by_label = {item.get("label"): item for item in issue_colony_results}
    comparisons: list[dict[str, Any]] = []

    for intervention in INTERVENTION_LIBRARY:
        affected = []
        total_score = 0.0
        for label in intervention["matched_issues"]:
            if label in issue_by_label:
                affected.append(label)
                total_score += float(issue_by_label[label].get("selection_score", 0))

        if not affected:
            continue

        normalized_score = total_score / max(len(affected), 1)
        expected_effect = (
            "高"
            if normalized_score >= 0.72
            else "中"
            if normalized_score >= 0.5
            else "低"
        )
        supporting_signals = []
        for label in affected:
            issue_result = issue_result_by_label.get(label) or {}
            top_scenario = (issue_result.get("top_scenarios") or [{}])[0]
            if top_scenario.get("description"):
                supporting_signals.append(top_scenario["description"])

        comparisons.append({
            "intervention_id": intervention["intervention_id"],
            "label": intervention["label"],
            "change_summary": intervention["change_summary"],
            "affected_issues": affected,
            "comparison_mode": "heuristic",
            "expected_effect": expected_effect,
            "observed_uplift": None,
            "observed_downside": None,
            "uncertainty": None,
            "supporting_signals": supporting_signals[:3],
            "supporting_evidence": [],
        })

    return comparisons
