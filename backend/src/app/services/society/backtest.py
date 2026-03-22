"""Backtest helpers for society-first simulations.

Keeps historical-case comparisons in JSON so the MVP can compare predicted
issue scenarios against later observed outcomes without introducing new DB
tables yet.
"""

from __future__ import annotations

import math
import re
import uuid
from statistics import pstdev
from typing import Any


BACKTEST_SCHEMA_VERSION = 1

METRIC_DEFINITIONS: dict[str, dict[str, str]] = {
    "adoption_rate": {"label": "採用率", "direction": "up"},
    "conversion_rate": {"label": "転換率", "direction": "up"},
    "trust_score": {"label": "信頼スコア", "direction": "up"},
    "sentiment_score": {"label": "感情スコア", "direction": "up"},
    "referral_rate": {"label": "紹介率", "direction": "up"},
    "revenue_index": {"label": "売上指数", "direction": "up"},
    "approval_rate": {"label": "承認率", "direction": "up"},
    "compliance_readiness": {"label": "規制準備度", "direction": "up"},
    "regulatory_risk": {"label": "規制リスク", "direction": "down"},
    "complaint_rate": {"label": "苦情率", "direction": "down"},
}

INTERVENTION_METRICS: dict[str, list[str]] = {
    "price_reduction": ["adoption_rate", "conversion_rate", "revenue_index"],
    "regulatory_alignment": ["approval_rate", "compliance_readiness", "regulatory_risk", "trust_score"],
    "message_refinement": ["sentiment_score", "trust_score", "referral_rate", "conversion_rate"],
}

MATCHING_RULES = {
    "issue_label": "outcome.issue_label と predicted issue label の一致を優先",
    "scenario_text": "予測シナリオ説明と actual_scenario/summary の 2-gram Jaccard overlap",
    "tags": "outcome.tags と issue/scenario text の部分一致",
    "thresholds": {
        "hit": 0.67,
        "partial_hit": 0.42,
    },
    "weights": {
        "issue_label": 0.45,
        "scenario_text": 0.4,
        "tags": 0.15,
    },
}

BACKTEST_INPUT_FORMAT = {
    "schema_version": BACKTEST_SCHEMA_VERSION,
    "historical_cases": [
        {
            "case_id": "case-001",
            "title": "2025 関西ローンチ",
            "observed_at": "2025-10-01",
            "linked_simulation_id": "optional-simulation-id",
            "linked_report_id": "optional-report-id",
            "baseline_metrics": {
                "adoption_rate": 0.18,
                "conversion_rate": 0.09,
                "trust_score": 0.42,
                "regulatory_risk": 0.61,
            },
            "outcome": {
                "issue_label": "価格受容性",
                "summary": "価格改定後も導入は慎重だが、試験導入は増えた",
                "actual_scenario": "価格障壁で本格導入は遅れるが、トライアルは増える",
                "metrics": {
                    "adoption_rate": 0.27,
                    "conversion_rate": 0.13,
                    "trust_score": 0.48,
                    "regulatory_risk": 0.55,
                },
                "tags": ["価格", "導入", "試験利用"],
            },
            "interventions": [
                {
                    "intervention_id": "price_reduction",
                    "label": "価格変更",
                    "baseline_metrics": {
                        "adoption_rate": 0.18,
                        "conversion_rate": 0.09,
                    },
                    "outcome_metrics": {
                        "adoption_rate": 0.27,
                        "conversion_rate": 0.13,
                    },
                    "evidence": [
                        "初月の採用率が 9pt 改善",
                        "価格反論率が低下",
                    ],
                }
            ],
        }
    ],
}


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_compact(value: str | None) -> str:
    text = _clean_text(value).lower()
    return re.sub(r"[\s、。・,./!！?？:：;；()\[\]{}「」『』【】\-_=+]+", "", text)


def _ngrams(value: str | None, *, size: int = 2) -> set[str]:
    compact = _normalize_compact(value)
    if not compact:
        return set()
    if len(compact) <= size:
        return {compact}
    return {compact[i : i + size] for i in range(len(compact) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _verdict(score: float) -> str:
    if score >= float(MATCHING_RULES["thresholds"]["hit"]):
        return "hit"
    if score >= float(MATCHING_RULES["thresholds"]["partial_hit"]):
        return "partial_hit"
    return "miss"


def _format_delta(value: float) -> str:
    return f"{value * 100:+.1f}pt"


def _metric_label(metric: str) -> str:
    return str(METRIC_DEFINITIONS.get(metric, {}).get("label") or metric)


def build_empty_backtest_result() -> dict[str, Any]:
    return {
        "schema_version": BACKTEST_SCHEMA_VERSION,
        "input_format": BACKTEST_INPUT_FORMAT,
        "matching_rules": MATCHING_RULES,
        "historical_cases": [],
        "cases": [],
        "summary": {
            "case_count": 0,
            "compared_case_count": 0,
            "hit_count": 0,
            "partial_hit_count": 0,
            "miss_count": 0,
            "hit_rate": 0.0,
            "issue_hit_count": 0,
            "issue_hit_rate": 0.0,
        },
        "status": "no_data",
    }


def _collect_predicted_scenarios(payload: dict[str, Any]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for colony in payload.get("issue_colonies") or []:
        issue_id = str(colony.get("issue_id") or "")
        issue_label = str(colony.get("label") or "")
        for scenario in colony.get("top_scenarios") or []:
            description = _clean_text(scenario.get("description"))
            if not description:
                continue
            collected.append({
                "issue_id": issue_id,
                "issue_label": issue_label,
                "description": description,
                "scenario_score": float(scenario.get("scenario_score", scenario.get("probability", 0)) or 0),
            })
    if collected:
        return collected

    for scenario in payload.get("scenarios") or []:
        description = _clean_text(scenario.get("description"))
        if not description:
            continue
        issue_label = ""
        match = re.match(r"^\[([^\]]+)\]\s*(.+)$", description)
        if match:
            issue_label = match.group(1)
            description = match.group(2)
        collected.append({
            "issue_id": "",
            "issue_label": issue_label,
            "description": description,
            "scenario_score": float(scenario.get("scenario_score", scenario.get("probability", 0)) or 0),
        })
    return collected


def _normalize_case(case: dict[str, Any], index: int) -> dict[str, Any]:
    outcome = dict(case.get("outcome") or {})
    return {
        "case_id": str(case.get("case_id") or f"case-{index + 1}"),
        "title": _clean_text(case.get("title")) or f"Historical Case {index + 1}",
        "observed_at": _clean_text(case.get("observed_at")),
        "linked_simulation_id": _clean_text(case.get("linked_simulation_id")),
        "linked_report_id": _clean_text(case.get("linked_report_id")),
        "baseline_metrics": {
            str(metric): float(value)
            for metric, value in (case.get("baseline_metrics") or {}).items()
            if isinstance(value, (int, float))
        },
        "outcome": {
            "issue_label": _clean_text(outcome.get("issue_label")),
            "summary": _clean_text(outcome.get("summary")),
            "actual_scenario": _clean_text(outcome.get("actual_scenario")),
            "metrics": {
                str(metric): float(value)
                for metric, value in (outcome.get("metrics") or {}).items()
                if isinstance(value, (int, float))
            },
            "tags": [
                _clean_text(tag)
                for tag in (outcome.get("tags") or [])
                if _clean_text(tag)
            ],
        },
        "interventions": [
            {
                "intervention_id": _clean_text(intervention.get("intervention_id")),
                "label": _clean_text(intervention.get("label")),
                "baseline_metrics": {
                    str(metric): float(value)
                    for metric, value in (intervention.get("baseline_metrics") or {}).items()
                    if isinstance(value, (int, float))
                },
                "outcome_metrics": {
                    str(metric): float(value)
                    for metric, value in (intervention.get("outcome_metrics") or {}).items()
                    if isinstance(value, (int, float))
                },
                "evidence": [
                    _clean_text(item)
                    for item in (intervention.get("evidence") or [])
                    if _clean_text(item)
                ],
            }
            for intervention in (case.get("interventions") or [])
        ],
    }


def _score_prediction(predicted: dict[str, Any], actual_outcome: dict[str, Any]) -> dict[str, Any]:
    actual_issue = _clean_text(actual_outcome.get("issue_label"))
    actual_text = _clean_text(actual_outcome.get("actual_scenario")) or _clean_text(actual_outcome.get("summary"))
    predicted_issue = _clean_text(predicted.get("issue_label"))
    predicted_text = _clean_text(predicted.get("description"))
    tags = [tag for tag in actual_outcome.get("tags") or [] if tag]

    label_match = 0.0
    if actual_issue and predicted_issue:
        if actual_issue == predicted_issue:
            label_match = 1.0
        elif actual_issue in predicted_issue or predicted_issue in actual_issue:
            label_match = 0.7
    elif predicted_issue and predicted_issue in actual_text:
        label_match = 0.55

    overlap = _jaccard(_ngrams(predicted_text), _ngrams(actual_text))

    tag_hits = 0
    searchable_text = f"{predicted_issue} {predicted_text}"
    for tag in tags:
        if tag and tag in searchable_text:
            tag_hits += 1
    tag_overlap = tag_hits / max(len(tags), 1) if tags else 0.0

    score = round(
        label_match * float(MATCHING_RULES["weights"]["issue_label"])
        + overlap * float(MATCHING_RULES["weights"]["scenario_text"])
        + tag_overlap * float(MATCHING_RULES["weights"]["tags"]),
        3,
    )

    reasons = []
    if label_match:
        reasons.append("issue_label_match")
    if overlap >= 0.2:
        reasons.append("scenario_text_overlap")
    if tag_overlap:
        reasons.append("outcome_tag_overlap")

    return {
        "issue_id": predicted.get("issue_id", ""),
        "issue_label": predicted_issue,
        "scenario_description": predicted_text,
        "predicted_score": float(predicted.get("scenario_score", 0) or 0),
        "actual_summary": _clean_text(actual_outcome.get("summary")),
        "actual_scenario": _clean_text(actual_outcome.get("actual_scenario")),
        "match_score": score,
        "label_match": round(label_match, 3),
        "text_overlap": round(overlap, 3),
        "tag_overlap": round(tag_overlap, 3),
        "verdict": _verdict(score),
        "reasons": reasons,
    }


def run_backtest_analysis(
    society_first_result: dict[str, Any] | None,
    historical_cases: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    payload = society_first_result or {}
    cases = historical_cases or []
    result = build_empty_backtest_result()
    result["historical_cases"] = [_normalize_case(case, index) for index, case in enumerate(cases)]

    predicted_items = _collect_predicted_scenarios(payload)
    if not predicted_items or not result["historical_cases"]:
        result["status"] = "ready" if result["historical_cases"] else "no_data"
        return result

    analyzed_cases: list[dict[str, Any]] = []
    best_verdict_counts = {"hit": 0, "partial_hit": 0, "miss": 0}
    total_issue_hits = 0

    for case in result["historical_cases"]:
        matches = [
            _score_prediction(predicted, case["outcome"])
            for predicted in predicted_items
        ]
        matches.sort(
            key=lambda item: (
                item["match_score"],
                item["predicted_score"],
            ),
            reverse=True,
        )
        best_match = matches[0] if matches else None
        verdict = str(best_match.get("verdict") if best_match else "miss")
        best_verdict_counts[verdict] += 1

        issue_results: list[dict[str, Any]] = []
        issue_seen: set[str] = set()
        for match in matches:
            issue_label = str(match.get("issue_label") or "")
            if not issue_label or issue_label in issue_seen:
                continue
            issue_seen.add(issue_label)
            issue_results.append({
                "issue_label": issue_label,
                "verdict": match["verdict"],
                "match_score": match["match_score"],
                "scenario_description": match["scenario_description"],
            })
            if match["verdict"] == "hit":
                total_issue_hits += 1

        analyzed_cases.append({
            **case,
            "best_match": best_match,
            "scenario_matches": matches[:5],
            "issue_results": issue_results,
            "summary": {
                "hit_count": sum(1 for item in matches if item["verdict"] == "hit"),
                "partial_hit_count": sum(1 for item in matches if item["verdict"] == "partial_hit"),
                "miss_count": sum(1 for item in matches if item["verdict"] == "miss"),
            },
        })

    case_count = len(analyzed_cases)
    result["cases"] = analyzed_cases
    result["summary"] = {
        "case_count": case_count,
        "compared_case_count": case_count,
        "hit_count": best_verdict_counts["hit"],
        "partial_hit_count": best_verdict_counts["partial_hit"],
        "miss_count": best_verdict_counts["miss"],
        "hit_rate": round(best_verdict_counts["hit"] / max(case_count, 1), 3),
        "issue_hit_count": total_issue_hits,
        "issue_hit_rate": round(total_issue_hits / max(sum(len(case["issue_results"]) for case in analyzed_cases), 1), 3),
    }
    result["status"] = "ready"
    return result


def _signed_metric_delta(metric: str, baseline: float, outcome: float) -> float:
    direction = str(METRIC_DEFINITIONS.get(metric, {}).get("direction") or "up")
    return outcome - baseline if direction == "up" else baseline - outcome


def _collect_metric_observations(
    *,
    intervention_id: str,
    backtest_result: dict[str, Any],
    affected_issues: list[str],
) -> list[dict[str, Any]]:
    metrics = INTERVENTION_METRICS.get(intervention_id) or []
    cases = backtest_result.get("cases") or []
    observations: list[dict[str, Any]] = []

    for case in cases:
        matched_issues = {
            str(item.get("issue_label") or "")
            for item in case.get("issue_results") or []
            if item.get("verdict") in {"hit", "partial_hit"}
        }
        outcome_issue = str((case.get("outcome") or {}).get("issue_label") or "")
        if outcome_issue:
            matched_issues.add(outcome_issue)
        if affected_issues and matched_issues and matched_issues.isdisjoint(set(affected_issues)):
            continue

        case_baseline = dict(case.get("baseline_metrics") or {})
        outcome_metrics = dict((case.get("outcome") or {}).get("metrics") or {})
        for intervention in case.get("interventions") or []:
            if str(intervention.get("intervention_id") or "") != intervention_id:
                continue
            baseline_metrics = dict(intervention.get("baseline_metrics") or {}) or case_baseline
            observed_metrics = dict(intervention.get("outcome_metrics") or {}) or outcome_metrics
            evidence = list(intervention.get("evidence") or [])

            for metric in metrics:
                baseline = baseline_metrics.get(metric)
                outcome = observed_metrics.get(metric)
                if not isinstance(baseline, (int, float)) or not isinstance(outcome, (int, float)):
                    continue
                delta = _signed_metric_delta(metric, float(baseline), float(outcome))
                observations.append({
                    "case_id": case.get("case_id"),
                    "title": case.get("title"),
                    "metric": metric,
                    "metric_label": _metric_label(metric),
                    "baseline": round(float(baseline), 4),
                    "outcome": round(float(outcome), 4),
                    "signed_delta": round(delta, 4),
                    "verdict": str((case.get("best_match") or {}).get("verdict") or "miss"),
                    "evidence": evidence,
                })
    return observations


def overlay_observed_intervention_comparison(
    comparisons: list[dict[str, Any]],
    backtest_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not comparisons:
        return []

    backtest = backtest_result or {}
    if (backtest.get("summary") or {}).get("case_count", 0) <= 0:
        return [dict(item) for item in comparisons]

    observed_comparisons: list[dict[str, Any]] = []
    for comparison in comparisons:
        item = dict(comparison)
        observations = _collect_metric_observations(
            intervention_id=str(item.get("intervention_id") or ""),
            backtest_result=backtest,
            affected_issues=list(item.get("affected_issues") or []),
        )
        if not observations:
            observed_comparisons.append(item)
            continue

        deltas = [float(obs["signed_delta"]) for obs in observations]
        positive = [delta for delta in deltas if delta > 0]
        negative = [delta for delta in deltas if delta < 0]
        uplift = round(sum(positive) / max(len(positive), 1), 4) if positive else 0.0
        downside = round(abs(sum(negative) / max(len(negative), 1)), 4) if negative else 0.0
        spread = pstdev(deltas) if len(deltas) > 1 else 0.0
        uncertainty = round(min(1.0, (1 / math.sqrt(len(deltas))) + spread), 4)

        evidence = []
        for observation in observations[:5]:
            evidence.append({
                "case_id": observation["case_id"],
                "title": observation["title"],
                "metric": observation["metric"],
                "metric_label": observation["metric_label"],
                "baseline": observation["baseline"],
                "outcome": observation["outcome"],
                "signed_delta": observation["signed_delta"],
                "summary": (
                    f"{observation['title']}: {observation['metric_label']} "
                    f"{_format_delta(observation['signed_delta'])}"
                ),
                "evidence": observation["evidence"][:3],
            })

        item.update({
            "comparison_mode": "observed",
            "expected_effect": f"uplift {_format_delta(uplift)} / downside {_format_delta(-downside)}",
            "observed_uplift": uplift,
            "observed_downside": downside,
            "uncertainty": uncertainty,
            "observed_case_count": len({str(obs['case_id']) for obs in observations}),
            "supporting_evidence": evidence,
            "supporting_signals": [
                entry["summary"]
                for entry in evidence
            ],
        })
        observed_comparisons.append(item)

    return observed_comparisons


def prepare_backtest_payload(
    society_first_result: dict[str, Any] | None,
    historical_cases: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    result = run_backtest_analysis(society_first_result, historical_cases)
    return {
        **result,
        "id": str(uuid.uuid4()),
    }
