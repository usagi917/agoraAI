"""Intervention planning for meta simulations."""

from __future__ import annotations

import re
from typing import Any

from src.app.services.society.issue_miner import build_intervention_comparison


CHANGE_TYPE_KEYWORDS = {
    "pricing": ("価格", "値段", "割引", "課金"),
    "message": ("訴求", "メッセージ", "ブランド", "認知", "信頼"),
    "regulatory": ("規制", "法規", "行政", "コンプライアンス"),
    "product": ("機能", "品質", "UX", "導入", "プロダクト"),
    "channel": ("チャネル", "営業", "販売", "パートナー", "流通"),
    "ops": ("供給", "物流", "調達", "運用", "サポート"),
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _infer_change_type(text: str) -> str:
    normalized = str(text or "")
    for change_type, keywords in CHANGE_TYPE_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return change_type
    return "product"


def _normalize_target_issues(
    text: str,
    selected_issues: list[dict[str, Any]],
) -> list[str]:
    labels = [str(issue.get("label") or "") for issue in selected_issues if issue.get("label")]
    matched = [label for label in labels if label and label in text]
    if matched:
        return matched[:3]
    return labels[:2]


def _normalize_action_label(action: dict[str, Any], index: int) -> str:
    return (
        str(action.get("action") or "").strip()
        or str(action.get("title") or "").strip()
        or f"Intervention {index}"
    )


def _normalize_hypothesis(action: dict[str, Any], label: str) -> str:
    return (
        str(action.get("evidence") or "").strip()
        or str(action.get("reasoning") or "").strip()
        or f"{label} により採用障壁と不確実性を下げる"
    )


def _estimate_expected_delta(
    confidence: float,
    issue_coverage: float,
    overall_confidence: float,
) -> float:
    return round(
        min(0.95, max(0.08, confidence * 0.45 + issue_coverage * 0.30 + overall_confidence * 0.25)),
        4,
    )


def _score_candidate(candidate: dict[str, Any], selected_issue_count: int) -> float:
    issue_coverage = len(candidate.get("target_issues") or []) / max(selected_issue_count, 1)
    selection_score = (
        _safe_float(candidate.get("confidence"), 0.0) * 0.5
        + _safe_float(candidate.get("expected_delta"), 0.0) * 0.3
        + issue_coverage * 0.2
    )
    return round(selection_score, 4)


def _fallback_candidates(
    selected_issues: list[dict[str, Any]],
    issue_colonies: list[dict[str, Any]],
    overall_confidence: float,
) -> list[dict[str, Any]]:
    fallback = build_intervention_comparison(selected_issues, issue_colonies)
    effect_map = {"高": 0.72, "中": 0.55, "低": 0.35}
    candidates = []
    for index, item in enumerate(fallback, start=1):
        candidates.append({
            "intervention_id": str(item.get("intervention_id") or f"fallback-{index}"),
            "label": str(item.get("label") or f"Fallback {index}"),
            "change_type": _infer_change_type(str(item.get("label") or "")),
            "hypothesis": str(item.get("change_summary") or "").strip(),
            "target_issues": list(item.get("affected_issues") or []),
            "expected_effect": str(item.get("expected_effect") or "中"),
            "expected_delta": effect_map.get(str(item.get("expected_effect") or "中"), 0.45),
            "confidence": round(max(overall_confidence * 0.8, 0.35), 4),
            "implementation_cost": "medium",
        })
    return candidates


def plan_interventions(
    pm_result: dict[str, Any],
    selected_issues: list[dict[str, Any]],
    issue_colonies: list[dict[str, Any]],
    *,
    max_candidates: int = 3,
) -> list[dict[str, Any]]:
    overall_confidence = _safe_float(pm_result.get("overall_confidence"), 0.5)
    sections = dict(pm_result.get("sections") or {})
    top_actions = list(sections.get("top_5_actions") or [])

    candidates: list[dict[str, Any]] = []
    for index, action in enumerate(top_actions, start=1):
        label = _normalize_action_label(action, index)
        target_issues = _normalize_target_issues(label + " " + _normalize_hypothesis(action, label), selected_issues)
        issue_coverage = len(target_issues) / max(len(selected_issues), 1)
        confidence = _safe_float(action.get("confidence"), overall_confidence)
        expected_delta = _estimate_expected_delta(confidence, issue_coverage, overall_confidence)
        change_type = _infer_change_type(label)

        candidate = {
            "intervention_id": f"pm-{index}",
            "label": label,
            "change_type": change_type,
            "hypothesis": _normalize_hypothesis(action, label),
            "target_issues": target_issues,
            "expected_effect": "高" if expected_delta >= 0.72 else "中" if expected_delta >= 0.5 else "低",
            "expected_delta": expected_delta,
            "confidence": round(confidence, 4),
            "implementation_cost": "high" if change_type in {"product", "ops"} else "medium",
        }
        candidates.append(candidate)

    if not candidates:
        candidates = _fallback_candidates(selected_issues, issue_colonies, overall_confidence)

    deduped: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for candidate in candidates:
        normalized_label = re.sub(r"\s+", " ", str(candidate.get("label") or "").strip().lower())
        if not normalized_label or normalized_label in seen_labels:
            continue
        seen_labels.add(normalized_label)
        deduped.append(candidate)

    for candidate in deduped:
        candidate["selection_score"] = _score_candidate(candidate, len(selected_issues))

    deduped.sort(
        key=lambda item: (
            _safe_float(item.get("selection_score"), 0.0),
            _safe_float(item.get("confidence"), 0.0),
            _safe_float(item.get("expected_delta"), 0.0),
        ),
        reverse=True,
    )
    return deduped[:max_candidates]


def select_intervention(interventions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not interventions:
        return None
    return dict(interventions[0])
