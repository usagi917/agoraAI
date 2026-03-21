"""Independent verification helpers for generated outputs."""

from __future__ import annotations

from typing import Any


def _build_verification(
    *,
    issues: list[str],
    warnings: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warning_list = warnings or []
    status = "passed" if not issues else "failed"
    score = max(0.0, 1.0 - 0.25 * len(issues) - 0.05 * len(warning_list))
    return {
        "status": status,
        "score": round(score, 3),
        "issues": issues,
        "warnings": warning_list,
        "metrics": metrics or {},
    }


def verify_world_build_result(payload: dict[str, Any] | None) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    data = payload or {}
    entities = data.get("entities") or []
    relations = data.get("relations") or []
    timeline = data.get("timeline") or []
    entity_ids = [str(entity.get("id", "")) for entity in entities if entity.get("id")]

    if not entities:
        issues.append("no_entities")
    if not data.get("world_summary"):
        issues.append("missing_world_summary")
    if len(entity_ids) != len(set(entity_ids)):
        issues.append("duplicate_entity_ids")
    if not timeline:
        warnings.append("timeline_empty")

    entity_id_set = set(entity_ids)
    orphan_relations = 0
    for relation in relations:
        source = str(relation.get("source", ""))
        target = str(relation.get("target", ""))
        if source not in entity_id_set or target not in entity_id_set:
            orphan_relations += 1
    if orphan_relations:
        issues.append("orphan_relations")

    return _build_verification(
        issues=issues,
        warnings=warnings,
        metrics={
            "entity_count": len(entities),
            "relation_count": len(relations),
            "timeline_event_count": len(timeline),
            "orphan_relation_count": orphan_relations,
        },
    )


def verify_scenarios(scenarios: list[dict[str, Any]] | None) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    items = scenarios or []

    if not items:
        issues.append("no_scenarios")

    out_of_range = 0
    described = 0
    for scenario in items:
        probability = scenario.get("probability", scenario.get("scenario_score", 0))
        if not isinstance(probability, (int, float)) or probability < 0 or probability > 1:
            out_of_range += 1
        if str(scenario.get("description", "")).strip():
            described += 1

    if out_of_range:
        issues.append("scenario_probability_out_of_range")
    if items and described < len(items):
        warnings.append("scenario_description_missing")

    return _build_verification(
        issues=issues,
        warnings=warnings,
        metrics={
            "scenario_count": len(items),
            "described_scenarios": described,
            "out_of_range_count": out_of_range,
        },
    )


def verify_pm_board_result(payload: dict[str, Any] | None) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    data = payload or {}
    sections = data.get("sections") or {}
    required_sections = {
        "core_question",
        "assumptions",
        "uncertainties",
        "risks",
        "winning_hypothesis",
        "customer_validation_plan",
        "market_view",
        "gtm_hypothesis",
        "mvp_scope",
        "plan_30_60_90",
        "top_5_actions",
    }
    missing_sections = sorted(
        section_name for section_name in required_sections if section_name not in sections
    )
    if missing_sections:
        issues.append("missing_pm_sections")

    if not str(sections.get("core_question", "")).strip():
        issues.append("missing_core_question")
    if not sections.get("top_5_actions"):
        issues.append("missing_top_actions")
    if not sections.get("winning_hypothesis"):
        issues.append("missing_winning_hypothesis")

    overall_confidence = data.get("overall_confidence", 0)
    if not isinstance(overall_confidence, (int, float)) or overall_confidence < 0 or overall_confidence > 1:
        issues.append("overall_confidence_out_of_range")

    contradictions = data.get("contradictions") or []
    if not contradictions:
        warnings.append("no_contradictions_recorded")

    return _build_verification(
        issues=issues,
        warnings=warnings,
        metrics={
            "section_count": len(sections),
            "missing_section_count": len(missing_sections),
            "contradiction_count": len(contradictions),
            "top_action_count": len(sections.get("top_5_actions") or []),
        },
    )


def verify_report_content(
    content: str,
    *,
    required_sections: list[str],
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    report_text = content or ""
    missing_sections = [
        title for title in required_sections
        if f"## {title}" not in report_text and f"# {title}" not in report_text
    ]

    if not report_text.strip():
        issues.append("empty_report_content")
    if missing_sections:
        issues.append("missing_report_sections")
    if len(report_text.strip()) < 400:
        warnings.append("report_too_short")

    quality_status = str((quality or {}).get("status") or "")
    if quality_status == "unsupported":
        issues.append("unsupported_quality")
    elif quality_status == "draft":
        warnings.append("draft_quality")

    return _build_verification(
        issues=issues,
        warnings=warnings,
        metrics={
            "required_section_count": len(required_sections),
            "missing_section_count": len(missing_sections),
            "content_length": len(report_text),
            "quality_status": quality_status or "unknown",
        },
    )


def merge_verification_results(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    nested_metrics: dict[str, Any] = {}

    for name, result in results.items():
        for issue in result.get("issues", []):
            issues.append(f"{name}:{issue}")
        for warning in result.get("warnings", []):
            warnings.append(f"{name}:{warning}")
        nested_metrics[name] = result.get("metrics", {})

    merged = _build_verification(
        issues=issues,
        warnings=warnings,
        metrics=nested_metrics,
    )
    merged["checks"] = results
    return merged


def ensure_verification_passed(verification: dict[str, Any], *, context: str) -> None:
    if verification.get("status") == "passed":
        return

    details = ",".join(str(issue) for issue in verification.get("issues", [])) or "verification_failed"
    raise ValueError(f"{context} verification failed: {details}")
