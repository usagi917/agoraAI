"""意思決定向けサマリーの共通ビルダー。"""

from __future__ import annotations

import re
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _coalesce(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        value = " / ".join(
            _clean_text(v)
            for v in value.values()
            if _clean_text(v)
        )
    elif isinstance(value, list):
        value = " / ".join(_clean_text(item) for item in value if _clean_text(item))
    text = str(value)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"`+", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _truncate(text: str, limit: int = 300) -> str:
    cleaned = _clean_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _first_sentence(text: Any, fallback: str = "", n: int = 2) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return fallback
    candidates = re.split(r"(?<=[。.!?])\s+|[。.!?\n]+", cleaned)
    sentences: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate:
            sentences.append(candidate)
            if len(sentences) >= n:
                break
    if sentences:
        return _truncate("。".join(sentences))
    return _truncate(cleaned or fallback)


def _sentence_list(text: Any, *, limit: int = 5) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[。.!?])\s+|[。.!?\n]+", cleaned)
    items: list[str] = []
    for part in parts:
        part = part.strip(" -")
        if not part:
            continue
        items.append(_truncate(part))
        if len(items) >= limit:
            break
    if not items:
        return [_truncate(cleaned)]
    return items


def _dedupe(items: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        value = _clean_text(item.get(key))
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(item)
    return result


def _normalize_option(label: str, upside: str, downside: str, fit: str, when_to_choose: str) -> dict[str, str]:
    return {
        "label": label,
        "upside": _truncate(upside, 200),
        "downside": _truncate(downside, 200),
        "fit": _truncate(fit, 200),
        "when_to_choose": _truncate(when_to_choose, 200),
    }


def _legacy_fields(
    *,
    score: float,
    option_comparison: list[dict[str, Any]],
    strongest_counterargument: str,
    risk_factors: list[dict[str, str]],
    recommended_actions: list[dict[str, Any]],
    time_horizon: dict[str, dict[str, str]],
    stakeholder_reactions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    options = [
        {
            "label": option.get("label", ""),
            "expected_effect": option.get("upside", ""),
            "risk": option.get("downside", ""),
        }
        for option in option_comparison[:3]
    ]
    return {
        "agreement_score": round(score, 4),
        "agreement_breakdown": {
            "society": round(score, 4),
            "council": round(max(score - 0.04, 0.0), 4),
            "synthesis": round(min(score + 0.03, 1.0), 4),
        },
        "options": options,
        "strongest_counterargument": _truncate(strongest_counterargument, 300),
        "risk_factors": risk_factors[:4],
        "next_steps": [action.get("action", "") for action in recommended_actions[:4] if action.get("action")],
        "time_horizon": time_horizon,
        "stakeholder_reactions": stakeholder_reactions or [],
    }


def _recommendation_from_score(score: float) -> str:
    if score >= 0.72:
        return "Go"
    if score <= 0.42:
        return "No-Go"
    return "条件付きGo"


def _recommendation_from_text(text: str, *, default_score: float = 0.58) -> str:
    cleaned = _clean_text(text)
    if re.search(r"見送|撤退|中止|No-Go|不採算|不可", cleaned, flags=re.IGNORECASE):
        return "No-Go"
    if re.search(r"推奨|実行|参入|着手|拡大|Go", cleaned, flags=re.IGNORECASE):
        return "Go"
    return _recommendation_from_score(default_score)


def _default_time_horizon(summary: str, blockers: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    blocker_summary = blockers[0]["question"] if blockers else "主要仮説の確認"
    return {
        "short_term": {
            "period": "30日",
            "prediction": _truncate(f"{blocker_summary}に対する初回検証を完了する"),
        },
        "mid_term": {
            "period": "90日",
            "prediction": _truncate(f"{_first_sentence(summary, '仮説') }の成立可否を見極める"),
        },
        "long_term": {
            "period": "12ヶ月",
            "prediction": _truncate("検証結果を踏まえて投資判断または拡大判断に進む"),
        },
    }


def _decision_usage_hint(
    *,
    score: float,
    quality: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
) -> tuple[str, str]:
    quality = dict(quality or {})
    verification = dict(verification or {})
    verification_status = _clean_text(verification.get("status"))
    quality_status = _clean_text(quality.get("status"))
    trust_level = _clean_text(quality.get("trust_level"))

    if verification_status == "passed" and quality_status == "verified" and score >= 0.7:
        return (
            "判断材料として使える",
            "recommendation を起点にしてよいが、guardrails と deal breakers を同時に確認して採用条件を固定する。",
        )
    if verification_status == "failed" or quality_status == "unsupported":
        return (
            "論点抽出用に使う",
            "結論をそのまま採用せず、critical_unknowns と evidence_gaps を follow-up の起点に使う。",
        )
    if trust_level == "low_trust" or score < 0.55:
        return (
            "仮説整理用に使う",
            "decision_summary よりも key_reasons / critical_unknowns / recommended_actions の組み合わせを優先して読む。",
        )
    return (
        "条件整理用に使う",
        "Go/No-Go を即断するより、どの前提が揃えば recommendation が強まるかを確認する用途に向く。",
    )


def enrich_decision_brief(
    brief: dict[str, Any],
    *,
    quality: dict[str, Any] | None = None,
    run_config: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    council_synthesis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = dict(brief or {})
    quality = dict(quality or {})
    run_config = dict(run_config or {})
    verification = dict(verification or {})
    scenarios = _as_list(scenarios)
    evidence_refs = _as_list(evidence_refs)

    score = _safe_float(enriched.get("agreement_score"), 0.0)
    evidence_mode = _clean_text(quality.get("evidence_mode") or run_config.get("evidence_mode") or "prefer")
    trust_level = _clean_text(quality.get("trust_level") or "unknown")
    verification_status = _clean_text(verification.get("status") or "n/a")
    verification_score = _safe_float(verification.get("score"), 0.0)
    usage_label, usage_detail = _decision_usage_hint(
        score=score,
        quality=quality,
        verification=verification,
    )

    scorecard = [
        {
            "label": "実行条件",
            "value": _truncate(
                f"mode={evidence_mode} / trust={trust_level or 'unknown'} / refs={len(evidence_refs)}",
                72,
            ),
            "detail": _truncate(
                (
                    f"quality={_clean_text(quality.get('status') or 'n/a')}。"
                    f" document={quality.get('document_refs_count', 0)} / prompt={quality.get('prompt_refs_count', 0)} を根拠に構成。"
                ),
                180,
            ),
        },
        {
            "label": "検証状態",
            "value": _truncate(
                f"{verification_status} ({verification_score * 100:.0f}%)" if verification else "n/a",
                72,
            ),
            "detail": _truncate(
                (
                    f"issues={len(_as_list(verification.get('issues')))} / warnings={len(_as_list(verification.get('warnings')))}。"
                    " failed の場合は結論確定ではなく追加確認の起点として扱う。"
                )
                if verification
                else "明示的な verification は未実行。quality と evidence refs を基準に読む。",
                180,
            ),
        },
        {
            "label": "使いどころ",
            "value": usage_label,
            "detail": _truncate(usage_detail, 180),
        },
    ]

    if scenarios:
        top_scenario = max(
            scenarios,
            key=lambda item: _safe_float(
                item.get("calibrated_probability"),
                _safe_float(item.get("scenario_score"), _safe_float(item.get("probability"), 0.0)),
            ),
        )
        scenario_score = _safe_float(
            top_scenario.get("calibrated_probability"),
            _safe_float(top_scenario.get("scenario_score"), _safe_float(top_scenario.get("probability"), 0.0)),
        )
        scorecard.insert(2, {
            "label": "最有力シナリオ",
            "value": _truncate(f"{scenario_score * 100:.0f}%: {_clean_text(top_scenario.get('description'))}", 96),
            "detail": _truncate(
                (
                    f"support={_safe_float(top_scenario.get('support_ratio'), _safe_float(top_scenario.get('agreement_ratio'), 0.0)) * 100:.0f}%"
                    f" / CI={top_scenario.get('ci') or 'n/a'}"
                    f" / claims={top_scenario.get('claim_count', 'n/a')}"
                ),
                180,
            ),
        })

    critical_unknowns = _as_list(enriched.get("critical_unknowns"))
    deal_breakers = _as_list(enriched.get("deal_breakers"))
    recommended_actions = _as_list(enriched.get("recommended_actions"))
    followup_prompts: list[str] = []
    if critical_unknowns:
        question = _clean_text(critical_unknowns[0].get("question"))
        if question:
            followup_prompts.append(_truncate(f"{question} が解消された場合、recommendation はどう変わるか", 160))
    if deal_breakers:
        trigger = _clean_text(deal_breakers[0].get("trigger"))
        if trigger:
            followup_prompts.append(_truncate(f"{trigger} が起きた場合の代替案と縮小プランは何か", 160))
    if recommended_actions:
        action = _clean_text(recommended_actions[0].get("action"))
        learning = _clean_text(recommended_actions[0].get("expected_learning"))
        if action:
            followup_prompts.append(_truncate(
                f"最優先アクション「{action}」で {learning or '期待した学習'} が得られなかった場合の次の一手は何か",
                160,
            ))

    enriched["decision_scorecard"] = scorecard
    enriched["followup_prompts"] = followup_prompts[:3]
    # Idempotent highlights injection — only add if not already present
    if council_synthesis and not enriched.get("conversation_highlights"):
        highlights = build_conversation_highlights(
            council_synthesis=council_synthesis,
            recommendation=_clean_text(enriched.get("recommendation") or ""),
        )
        if highlights:
            enriched["conversation_highlights"] = highlights
    return enriched


def build_single_decision_brief(
    *,
    prompt_text: str,
    report_content: str,
    sections: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sections = dict(sections or {})
    quality = dict(quality or {})
    summary_text = _coalesce(
        sections.get("executive_summary"),
        sections.get("simulation_summary"),
        report_content,
        prompt_text,
    )
    action_text = _coalesce(sections.get("recommended_actions"))
    risk_text = _coalesce(sections.get("risks"), sections.get("uncertainty"))
    assumptions_text = _coalesce(sections.get("input_assumptions"))

    trust_level = quality.get("trust_level")
    score = 0.65 if trust_level == "high_trust" else 0.56
    if quality.get("status") == "unsupported":
        score = 0.38

    recommendation = _recommendation_from_text(summary_text or report_content, default_score=score)

    key_reasons = [
        {
            "reason": sentence,
            "evidence": "single_report",
            "confidence": round(score, 4),
            "decision_impact": "初期判断の主因として扱う",
        }
        for sentence in _sentence_list(summary_text, limit=3)
    ]
    guardrails = [
        {
            "condition": sentence,
            "status": "未検証",
            "why_it_matters": "前提が崩れると結論の再評価が必要になる",
        }
        for sentence in _sentence_list(assumptions_text, limit=3)
    ]
    deal_breakers = [
        {
            "trigger": sentence,
            "impact": "意思決定を保留または縮小に切り替える",
            "recommended_response": "追加エビデンスを取得して再判定する",
        }
        for sentence in _sentence_list(risk_text, limit=3)
    ]
    critical_unknowns = [
        {
            "question": sentence,
            "importance": "結論を支える一次根拠がまだ薄い",
            "how_to_validate": "追加の文書根拠または実地検証で裏付ける",
            "decision_blocking": True,
        }
        for sentence in _sentence_list(_coalesce(sections.get("uncertainty"), risk_text), limit=3)
    ]
    recommended_actions = [
        {
            "action": sentence,
            "owner": "分析担当",
            "deadline": "次回レビューまで",
            "expected_learning": "判断を前に進める追加根拠を得る",
            "priority": "high" if index == 0 else "medium",
        }
        for index, sentence in enumerate(_sentence_list(action_text or "主要仮説を裏付ける追加検証を行う", limit=4))
    ]
    option_comparison = [
        _normalize_option(
            "即時着手",
            summary_text or "最も早く意思決定を進められる",
            risk_text or "未検証の前提を抱えたまま進む",
            "既に必要な前提が揃っている場合",
            "根拠が十分で競争速度が重要な場合",
        ),
        _normalize_option(
            "条件付きで進める",
            "リスクを管理しながら学習を進められる",
            "速度は落ちる",
            "主要な不確実性が残る場合",
            "追加検証で短期に判断精度を上げられる場合",
        ),
        _normalize_option(
            "判断保留",
            "誤投資を避けられる",
            "機会損失が出る",
            "一次根拠が不足している場合",
            "高インパクトの前提が未検証のままの場合",
        ),
    ]
    risk_factors = [
        {"condition": item["trigger"], "impact": item["impact"]}
        for item in deal_breakers[:3]
    ]
    time_horizon = _default_time_horizon(summary_text or prompt_text, critical_unknowns)
    strongest_counterargument = deal_breakers[0]["trigger"] if deal_breakers else "主要リスクの裏取りが不足している"
    primary_unknown = critical_unknowns[0]["question"] if critical_unknowns else "主要仮説の成否"
    primary_action = recommended_actions[0]["action"] if recommended_actions else "追加検証"
    score_pct = int(round(score * 100))
    trust_text = "文書根拠あり" if trust_level == "high_trust" else "根拠が限定的"

    brief = {
        "recommendation": recommendation,
        "decision_summary": _truncate(
            _first_sentence(summary_text, prompt_text)
            or "主要な結論は出ているが、追加検証を前提に判断すべき",
            180,
        ),
        "why_now": _truncate(
            f"まず {primary_unknown} を見極めつつ {primary_action} を進めると、{recommendation} を採る条件と保留条件を切り分けやすい。",
            220,
        ),
        "key_reasons": key_reasons,
        "guardrails": guardrails,
        "deal_breakers": deal_breakers,
        "critical_unknowns": critical_unknowns,
        "next_decisions": [
            {
                "decision": _truncate(f"{primary_unknown} を踏まえて {recommendation} を採るか判断する", 120),
                "owner": "意思決定者",
                "deadline": "次回レビュー",
                "input_needed": _truncate(
                    critical_unknowns[0]["how_to_validate"] if critical_unknowns else "追加根拠と主要リスクの解像度",
                    120,
                ),
            }
        ],
        "recommended_actions": recommended_actions,
        "option_comparison": option_comparison,
        "confidence_explainer": _truncate(
            f"判断スコアは {score_pct}%。{trust_text} の単独レポートなので、結論確定よりも前提整理と追加検証の優先順位づけに向く。",
            220,
        ),
        "evidence_gaps": [
            item["question"]
            for item in critical_unknowns[:3]
        ] or ["追加エビデンスが必要"],
    }
    brief.update(
        _legacy_fields(
            score=score,
            option_comparison=option_comparison,
            strongest_counterargument=strongest_counterargument,
            risk_factors=risk_factors,
            recommended_actions=recommended_actions,
            time_horizon=time_horizon,
        )
    )
    return brief


def build_pm_board_decision_brief(
    *,
    prompt_text: str,
    pm_result: dict[str, Any],
    scenarios: list[dict[str, Any]] | None = None,
    council_synthesis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sections = dict(pm_result.get("sections") or {})
    confidence = _safe_float(pm_result.get("overall_confidence"), 0.55)
    recommendation = _recommendation_from_score(confidence)

    winning = dict(sections.get("winning_hypothesis") or {})
    customer_validation = dict(sections.get("customer_validation_plan") or {})
    market_view = dict(sections.get("market_view") or {})
    gtm = dict(sections.get("gtm_hypothesis") or {})
    plan = dict(sections.get("plan_30_60_90") or {})
    assumptions = _as_list(sections.get("assumptions"))
    uncertainties = _as_list(sections.get("uncertainties"))
    risks = _as_list(sections.get("risks"))
    actions = _as_list(sections.get("top_5_actions"))
    contradictions = _as_list(pm_result.get("contradictions"))
    decision_points = _as_list(pm_result.get("key_decision_points"))
    scenario_list = _as_list(scenarios)

    top_scenario = None
    if scenario_list:
        top_scenario = max(
            scenario_list,
            key=lambda scenario: _safe_float(
                scenario.get("calibrated_probability"),
                _safe_float(scenario.get("scenario_score"), _safe_float(scenario.get("probability"), 0.0)),
            ),
        )

    decision_summary = _truncate(
        (
            f"{_clean_text(winning.get('if_true'))} を成立させられる前提なら {recommendation}。"
            if winning.get("if_true")
            else f"{_clean_text(sections.get('core_question') or prompt_text)} に対して {recommendation}。"
        ),
        180,
    )
    why_now = _truncate(
        (
            f"{_clean_text(customer_validation.get('timeline'))} 以内に主要仮説を検証できる計画があり、"
            "先に意思決定条件を明示しておくと検証の優先順位がぶれにくい。"
        )
        if customer_validation.get("timeline")
        else "市場仮説と顧客検証の優先順位を早期に固定しないと、調査と開発が並行でぶれやすい。"
    )

    key_reasons: list[dict[str, Any]] = []
    if winning.get("if_true") or winning.get("to_achieve"):
        key_reasons.append({
            "reason": _truncate(
                f"勝利仮説が {_clean_text(winning.get('if_true'))} を満たせば {_clean_text(winning.get('to_achieve'))} に到達できる設計になっている。",
                160,
            ),
            "evidence": _clean_text(winning.get("then_do") or "winning_hypothesis"),
            "confidence": _safe_float(winning.get("confidence"), confidence),
            "decision_impact": "Go/条件付きGo の中心根拠になる",
        })
    if market_view.get("market_size") or market_view.get("growth_rate"):
        key_reasons.append({
            "reason": _truncate(
                f"市場規模 {market_view.get('market_size', 'n/a')}、成長率 {market_view.get('growth_rate', 'n/a')} が成立しており、参入余地がある。",
                160,
            ),
            "evidence": "market_view",
            "confidence": round(min(confidence + 0.05, 0.95), 4),
            "decision_impact": "需要側の成立可能性を補強する",
        })
    if top_scenario:
        key_reasons.append({
            "reason": _truncate(
                f"最有力シナリオは「{_clean_text(top_scenario.get('description'))}」で、代替案比較の基準線として使える。",
                160,
            ),
            "evidence": _truncate(
                f"scenario_score={_safe_float(top_scenario.get('scenario_score'), _safe_float(top_scenario.get('probability'), 0.0)):.2f}",
                80,
            ),
            "confidence": round(min(confidence, 0.9), 4),
            "decision_impact": "どの条件を先に潰すべきかを定められる",
        })
    for action in actions[:2]:
        key_reasons.append({
            "reason": _truncate(_clean_text(action.get("decision_impact") or action.get("action"))),
            "evidence": _truncate(_clean_text(action.get("evidence") or action.get("additional_info_needed") or "top_5_actions")),
            "confidence": _safe_float(action.get("confidence"), confidence),
            "decision_impact": "次の一手が判断にどう効くかが明確",
        })
    key_reasons = _dedupe(key_reasons, key="reason")[:5]

    guardrails = [
        {
            "condition": _truncate(_clean_text(item.get("assumption"))),
            "status": (
                "概ね成立"
                if _safe_float(item.get("confidence"), 0.0) >= 0.75
                else "未検証"
            ),
            "why_it_matters": _truncate(_clean_text(item.get("impact_if_wrong") or "前提が崩れると判断の前提条件が変わる")),
        }
        for item in assumptions[:4]
        if _clean_text(item.get("assumption"))
    ]

    deal_breakers = [
        {
            "trigger": _truncate(_clean_text(item.get("risk"))),
            "impact": _truncate(_clean_text(item.get("impact") or "採用判断の前提が崩れる")),
            "recommended_response": _truncate(_clean_text(item.get("mitigation") or "先に検証計画を敷く")),
        }
        for item in risks[:3]
        if _clean_text(item.get("risk"))
    ]
    for contradiction in contradictions[:2]:
        issue = _clean_text(contradiction.get("issue"))
        if not issue:
            continue
        deal_breakers.append({
            "trigger": _truncate(issue),
            "impact": "判断条件の内部整合が崩れる",
            "recommended_response": _truncate(_clean_text(contradiction.get("resolution") or "どちらを優先するか先に決める")),
        })
    deal_breakers = _dedupe(deal_breakers, key="trigger")[:4]

    critical_unknowns = [
        {
            "question": _truncate(_clean_text(item.get("uncertainty"))),
            "importance": _truncate(_clean_text(item.get("impact") or item.get("risk_level") or "高")),
            "how_to_validate": _truncate(_clean_text(item.get("validation_method") or "追加ヒアリング")),
            "decision_blocking": True,
        }
        for item in uncertainties[:4]
        if _clean_text(item.get("uncertainty"))
    ]
    for point in decision_points[:3]:
        cleaned = _clean_text(point)
        if not cleaned:
            continue
        critical_unknowns.append({
            "question": _truncate(cleaned),
            "importance": "最終判断を左右する",
            "how_to_validate": "対応する検証アクションを完了する",
            "decision_blocking": True,
        })
    critical_unknowns = _dedupe(critical_unknowns, key="question")[:5]

    next_decisions = [
        {
            "decision": _truncate(_clean_text(point)),
            "owner": _clean_text(actions[index].get("owner")) if index < len(actions) else "責任者未定",
            "deadline": _clean_text(actions[index].get("deadline")) if index < len(actions) else "次回レビュー",
            "input_needed": _truncate(
                _clean_text(actions[index].get("additional_info_needed"))
                if index < len(actions)
                else "対応する追加検証結果"
            ),
        }
        for index, point in enumerate(decision_points[:4])
        if _clean_text(point)
    ]
    if not next_decisions and critical_unknowns:
        next_decisions = [
            {
                "decision": item["question"],
                "owner": "担当未設定",
                "deadline": "次回レビュー",
                "input_needed": item["how_to_validate"],
            }
            for item in critical_unknowns[:3]
        ]

    recommended_actions = [
        {
            "action": _truncate(_clean_text(item.get("action"))),
            "owner": _clean_text(item.get("owner") or "担当未設定"),
            "deadline": _clean_text(item.get("deadline") or "次回レビュー"),
            "expected_learning": _truncate(_clean_text(item.get("decision_impact") or item.get("evidence") or "主要仮説の精度が上がる")),
            "priority": (
                "high"
                if _safe_float(item.get("confidence"), 0.0) >= 0.75
                else "medium"
            ),
        }
        for item in actions[:5]
        if _clean_text(item.get("action"))
    ]
    if not recommended_actions:
        recommended_actions = [
            {
                "action": "主要仮説の顧客検証を行う",
                "owner": "PM",
                "deadline": "2週間",
                "expected_learning": "Go/No-Go の分岐条件が明確になる",
                "priority": "high",
            }
        ]

    target_customer = _clean_text(gtm.get("target_customer"))
    option_comparison = [
        _normalize_option(
            "推奨案: 条件付きで進める",
            winning.get("then_do") or "仮説を前進させながら学習できる",
            "未検証の前提を抱えたまま拡大すると失敗コストが大きい",
            target_customer or "主要顧客セグメントが明確な案件",
            "価格・顧客・実装条件を短期で検証できる場合",
        ),
        _normalize_option(
            "限定パイロット",
            "意思決定を遅らせずに実証データを積める",
            "売上成長は限定的",
            _clean_text(customer_validation.get("success_criteria") or "定量的な学習を取りたい案件"),
            "仮説は有望だが価格・定着率に不安がある場合",
        ),
        _normalize_option(
            "見送り / 再設計",
            "誤投資を避けられる",
            "市場機会を逃す可能性がある",
            _clean_text(deal_breakers[0]["trigger"]) if deal_breakers else "重大リスクが強い案件",
            "主要な deal breaker が短期に解消できない場合",
        ),
    ]

    strongest_counterargument = _coalesce(
        contradictions[0].get("issue") if contradictions else "",
        risks[0].get("risk") if risks else "",
        "主要仮説を支える一次検証がまだ足りない",
    )
    risk_factors = [
        {"condition": item["trigger"], "impact": item["impact"]}
        for item in deal_breakers[:4]
    ]
    time_horizon = {
        "short_term": {
            "period": "30日",
            "prediction": _truncate(_clean_text(plan.get("day_30", {}).get("goals")) or "検証計画を実行開始"),
        },
        "mid_term": {
            "period": "60-90日",
            "prediction": _truncate(_clean_text(plan.get("day_60", {}).get("goals")) or _clean_text(plan.get("day_90", {}).get("goals")) or "パイロット結果を確認"),
        },
        "long_term": {
            "period": "12ヶ月",
            "prediction": _truncate(_clean_text(winning.get("to_achieve")) or "有料転換や継続率を踏まえて拡大判断"),
        },
    }
    evidence_gaps = [
        _truncate(_clean_text(item.get("additional_info_needed")))
        for item in actions
        if _clean_text(item.get("additional_info_needed")) and _clean_text(item.get("additional_info_needed")) != "なし"
    ]
    if not evidence_gaps:
        evidence_gaps = [item["question"] for item in critical_unknowns[:3]]

    stakeholder_reactions: list[dict[str, Any]] = []
    for segment in _as_list(customer_validation.get("target_segments"))[:2]:
        stakeholder_reactions.append({
            "group": _truncate(_clean_text(segment), 60),
            "reaction": "検証対象として優先",
            "percentage": 60,
        })
    for player in _as_list(market_view.get("key_players"))[:2]:
        stakeholder_reactions.append({
            "group": _truncate(_clean_text(player.get("name")), 60),
            "reaction": _truncate(_clean_text(player.get("position") or player.get("strength") or "競合反応に注意"), 80),
            "percentage": 45,
        })

    unresolved_count = len([item for item in critical_unknowns if item.get("decision_blocking")])
    confidence_explainer = _truncate(
        (
            f"総合確信度は {confidence * 100:.0f}% 。"
            f"勝利仮説と市場仮説は一定の筋がある一方、未解決の判断論点が {unresolved_count} 件残るため"
            f" {recommendation} とする。"
        ),
        180,
    )

    brief = {
        "recommendation": recommendation,
        "decision_summary": decision_summary,
        "why_now": why_now,
        "key_reasons": key_reasons,
        "guardrails": guardrails,
        "deal_breakers": deal_breakers,
        "critical_unknowns": critical_unknowns,
        "next_decisions": next_decisions,
        "recommended_actions": recommended_actions,
        "option_comparison": option_comparison,
        "confidence_explainer": confidence_explainer,
        "evidence_gaps": evidence_gaps[:4],
    }
    brief.update(
        _legacy_fields(
            score=confidence,
            option_comparison=option_comparison,
            strongest_counterargument=strongest_counterargument,
            risk_factors=risk_factors,
            recommended_actions=recommended_actions,
            time_horizon=time_horizon,
            stakeholder_reactions=stakeholder_reactions[:4],
        )
    )
    highlights = build_conversation_highlights(
        council_synthesis=council_synthesis,
        pm_result=pm_result,
        recommendation=recommendation,
    )
    if highlights:
        brief["conversation_highlights"] = highlights
    return brief


def build_conversation_highlights(
    *,
    council_synthesis: dict[str, Any] | None = None,
    pm_result: dict[str, Any] | None = None,
    recommendation: str = "",
) -> dict[str, Any] | None:
    """Build rule-based conversation highlights from council synthesis or pm_result."""
    council = dict(council_synthesis or {})
    pm = dict(pm_result or {})
    pm_sections = dict(pm.get("sections") or {})

    # --- consensus ---
    consensus: list[dict[str, Any]] = []
    for raw in _as_list(council.get("consensus_points"))[:3]:
        point = _truncate(_clean_text(raw), 120)
        if point:
            consensus.append({"point": point, "impact": "合意形成済み"})
    if not consensus:
        for item in _as_list(pm_sections.get("assumptions"))[:3]:
            if _safe_float(item.get("confidence"), 0.0) >= 0.7:
                point = _truncate(_clean_text(item.get("assumption")), 120)
                if point:
                    consensus.append({"point": point, "impact": _truncate(_clean_text(item.get("impact_if_wrong") or "前提成立"), 120)})

    # --- conflicts ---
    conflicts: list[dict[str, Any]] = []
    for item in _as_list(council.get("disagreement_points"))[:3]:
        point = _truncate(_clean_text(item.get("topic") if isinstance(item, dict) else item), 120)
        impact = _truncate(_clean_text(item.get("impact") if isinstance(item, dict) else ""), 120)
        if point:
            conflicts.append({"point": point, "status": "unresolved", "impact": impact})
    if not conflicts:
        for item in _as_list(pm.get("contradictions"))[:3]:
            point = _truncate(_clean_text(item.get("issue") if isinstance(item, dict) else item), 120)
            if point:
                conflicts.append({"point": point, "status": "unresolved", "impact": "判断条件の内部整合が崩れる"})

    # --- turning_points ---
    turning_points: list[dict[str, Any]] = []
    for item in _as_list(council.get("stance_shifts"))[:3]:
        moment = _truncate(_clean_text(item.get("moment") if isinstance(item, dict) else item), 120)
        reason = _truncate(_clean_text(item.get("reason") if isinstance(item, dict) else ""), 120)
        if moment:
            turning_points.append({"moment": moment, "why_it_changed": reason})
    if not turning_points:
        for point in _as_list(pm.get("key_decision_points"))[:3]:
            cleaned = _truncate(_clean_text(point), 120)
            if cleaned:
                turning_points.append({"moment": cleaned, "why_it_changed": "主要判断点として記録"})

    # --- key_quotes ---
    key_quotes: list[dict[str, Any]] = []
    persuasive = council.get("most_persuasive_argument")
    if isinstance(persuasive, dict):
        speaker = _clean_text(persuasive.get("participant") or persuasive.get("speaker") or "")
        quote = _truncate(_clean_text(persuasive.get("argument") or persuasive.get("quote") or ""), 120)
        if quote:
            key_quotes.append({
                "speaker": speaker,
                "quote": quote,
                "decision_impact": "最も説得力があった主張",
            })
    if not key_quotes:
        winning = dict(pm_sections.get("winning_hypothesis") or {})
        if_true = _truncate(_clean_text(winning.get("if_true") or ""), 120)
        if if_true:
            key_quotes.append({
                "speaker": "winning_hypothesis",
                "quote": if_true,
                "decision_impact": "勝利仮説の条件",
            })

    # --- summary ---
    summary = _first_sentence(council.get("overall_assessment"), "")
    if not summary:
        core = _clean_text(pm_sections.get("core_question") or "")
        rec = _clean_text(recommendation)
        summary = _truncate(f"{core}: {rec}" if core and rec else core or rec, 160)

    # Return None if nothing was populated
    if not consensus and not conflicts and not turning_points and not key_quotes and not summary:
        return None

    source_phase = "council" if council_synthesis else "meeting"

    return {
        "summary": summary,
        "consensus": consensus[:3],
        "conflicts": conflicts[:3],
        "turning_points": turning_points[:3],
        "key_quotes": key_quotes[:3],
        "source_phase": source_phase,
    }


def build_pipeline_decision_brief(
    *,
    prompt_text: str,
    report_content: str,
    scenarios: list[dict[str, Any]] | None,
    pm_result: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(pm_result, dict) and pm_result.get("sections"):
        brief = build_pm_board_decision_brief(
            prompt_text=prompt_text,
            pm_result=pm_result,
            scenarios=scenarios,
        )
        if not brief.get("decision_summary"):
            brief["decision_summary"] = _truncate(_first_sentence(report_content, prompt_text), 180)
        if report_content:
            report_reason = {
                "reason": _truncate(_first_sentence(report_content, prompt_text), 160),
                "evidence": "pipeline_final_report",
                "confidence": brief.get("agreement_score", 0.0),
                "decision_impact": "統合レポート全体の結論を要約したもの",
            }
            reasons = [report_reason, *brief.get("key_reasons", [])]
            brief["key_reasons"] = _dedupe(reasons, key="reason")[:5]
        return brief

    return build_single_decision_brief(
        prompt_text=prompt_text,
        report_content=report_content,
    )


def render_decision_brief_markdown(brief: dict[str, Any], *, title: str = "Decision Memo") -> str:
    lines = [
        f"## {title}",
        "",
        f"**推奨**: {brief.get('recommendation', '未定')}",
    ]
    if brief.get("agreement_score") is not None:
        lines.append(f"**判断スコア**: {_safe_float(brief.get('agreement_score')) * 100:.0f}%")
    if brief.get("decision_summary"):
        lines.extend(["", _clean_text(brief.get("decision_summary"))])
    if brief.get("why_now"):
        lines.extend(["", "### なぜ今判断するのか", _clean_text(brief.get("why_now"))])

    key_reasons = _as_list(brief.get("key_reasons"))
    if key_reasons:
        lines.extend(["", "### 主な判断根拠"])
        for index, item in enumerate(key_reasons, start=1):
            line = f"{index}. {_clean_text(item.get('reason'))}"
            evidence = _clean_text(item.get("evidence"))
            impact = _clean_text(item.get("decision_impact"))
            confidence = item.get("confidence")
            annotations = []
            if evidence:
                annotations.append(f"根拠: {evidence}")
            if isinstance(confidence, (int, float)):
                annotations.append(f"確信度: {_safe_float(confidence) * 100:.0f}%")
            if impact:
                annotations.append(f"判断への効き方: {impact}")
            if annotations:
                line += f" ({' / '.join(annotations)})"
            lines.append(line)

    guardrails = _as_list(brief.get("guardrails"))
    if guardrails:
        lines.extend(["", "### この判断が成り立つ条件"])
        for item in guardrails:
            line = _clean_text(item.get("condition"))
            status = _clean_text(item.get("status"))
            why = _clean_text(item.get("why_it_matters"))
            if status:
                line += f" [{status}]"
            if why:
                line += f" - {why}"
            lines.append(f"- {line}")

    deal_breakers = _as_list(brief.get("deal_breakers"))
    if deal_breakers:
        lines.extend(["", "### 判断を覆すトリガー"])
        for item in deal_breakers:
            line = _clean_text(item.get("trigger"))
            impact = _clean_text(item.get("impact"))
            response = _clean_text(item.get("recommended_response"))
            details = " / ".join(part for part in [impact, response] if part)
            if details:
                line += f" - {details}"
            lines.append(f"- {line}")

    critical_unknowns = _as_list(brief.get("critical_unknowns"))
    if critical_unknowns:
        lines.extend(["", "### 追加で潰すべき論点"])
        for item in critical_unknowns:
            line = _clean_text(item.get("question"))
            importance = _clean_text(item.get("importance"))
            validate = _clean_text(item.get("how_to_validate"))
            details = " / ".join(part for part in [importance, f"検証: {validate}" if validate else ""] if part)
            if details:
                line += f" - {details}"
            lines.append(f"- {line}")

    next_decisions = _as_list(brief.get("next_decisions"))
    if next_decisions:
        lines.extend(["", "### 次に決めるべきこと"])
        for item in next_decisions:
            line = _clean_text(item.get("decision"))
            owner = _clean_text(item.get("owner"))
            deadline = _clean_text(item.get("deadline"))
            input_needed = _clean_text(item.get("input_needed"))
            details = " / ".join(part for part in [owner, deadline, input_needed] if part)
            if details:
                line += f" ({details})"
            lines.append(f"- {line}")

    actions = _as_list(brief.get("recommended_actions"))
    if actions:
        lines.extend(["", "### 推奨アクション"])
        for item in actions:
            line = _clean_text(item.get("action"))
            owner = _clean_text(item.get("owner"))
            deadline = _clean_text(item.get("deadline"))
            learning = _clean_text(item.get("expected_learning"))
            details = " / ".join(part for part in [owner, deadline, learning] if part)
            if details:
                line += f" - {details}"
            lines.append(f"- {line}")

    scorecard = _as_list(brief.get("decision_scorecard"))
    if scorecard:
        lines.extend(["", "### 判断の基準"])
        for item in scorecard:
            label = _clean_text(item.get("label"))
            value = _clean_text(item.get("value"))
            detail = _clean_text(item.get("detail"))
            line = " - ".join(part for part in [value, detail] if part)
            if label and line:
                lines.append(f"- {label}: {line}")
            elif label:
                lines.append(f"- {label}")

    highlights = brief.get("conversation_highlights")
    if isinstance(highlights, dict):
        lines.extend(["", "### 議論ハイライト"])
        hl_summary = _clean_text(highlights.get("summary"))
        if hl_summary:
            lines.append(hl_summary)
        for item in _as_list(highlights.get("consensus")):
            point = _clean_text(item.get("point"))
            impact = _clean_text(item.get("impact"))
            if point:
                lines.append(f"- 合意: {point}" + (f" ({impact})" if impact else ""))
        for item in _as_list(highlights.get("conflicts")):
            point = _clean_text(item.get("point"))
            status = _clean_text(item.get("status"))
            impact = _clean_text(item.get("impact"))
            if point:
                status_part = f" [{status}]" if status else ""
                impact_part = f" ({impact})" if impact else ""
                lines.append(f"- 対立: {point}{status_part}{impact_part}")
        for item in _as_list(highlights.get("turning_points")):
            moment = _clean_text(item.get("moment"))
            why = _clean_text(item.get("why_it_changed"))
            if moment:
                lines.append(f"- 転換点: {moment}" + (f" - {why}" if why else ""))
        for item in _as_list(highlights.get("key_quotes")):
            quote = _clean_text(item.get("quote"))
            speaker = _clean_text(item.get("speaker"))
            impact = _clean_text(item.get("decision_impact"))
            if quote:
                speaker_part = f" — {speaker}" if speaker else ""
                impact_part = f" ({impact})" if impact else ""
                lines.append(f"- > 「{quote}」{speaker_part}{impact_part}")

    followup_prompts = _as_list(brief.get("followup_prompts"))
    if followup_prompts:
        lines.extend(["", "### 深掘りに使う follow-up"])
        for item in followup_prompts:
            cleaned = _clean_text(item)
            if cleaned:
                lines.append(f"- {cleaned}")

    evidence_gaps = _as_list(brief.get("evidence_gaps"))
    if evidence_gaps:
        lines.extend(["", "### まだ足りない根拠"])
        for gap in evidence_gaps:
            cleaned = _clean_text(gap)
            if cleaned:
                lines.append(f"- {cleaned}")

    confidence_explainer = _clean_text(brief.get("confidence_explainer"))
    if confidence_explainer:
        lines.extend(["", "### 確信度の見立て", confidence_explainer])

    return "\n".join(lines).strip()
