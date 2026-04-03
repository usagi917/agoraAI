"""シナリオ比較サービス: ベースラインと介入シナリオの Decision Brief を比較する (Stream E)"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.audit_event import AuditEvent
from src.app.models.scenario_pair import ScenarioPair
from src.app.services.audit_trail_service import get_opinion_shifts
from src.app.services.decision_briefing import build_single_decision_brief

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure functions (no DB calls)
# ---------------------------------------------------------------------------


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_text_set(items: list[dict[str, Any]], key: str) -> set[str]:
    """Extract a set of non-empty string values from a list of dicts."""
    return {
        item[key]
        for item in items
        if isinstance(item, dict) and item.get(key)
    }


def build_delta_brief(baseline_brief: dict, intervention_brief: dict) -> dict:
    """Compare two decision briefs and extract meaningful differences.

    Pure function -- no DB or IO side-effects.

    Returns a dict with:
    - recommendation_change: tuple (before, after) if changed, else None
    - support_change: float change in agreement_score (intervention - baseline)
    - new_concerns: concerns (critical_unknowns questions) in intervention but not baseline
    - resolved_concerns: concerns in baseline that are absent in intervention
    - coalition_shifts: placeholder (populated by build_scenario_comparison)
    - key_differences: top 3 textual differences
    """
    # --- recommendation ---
    rec_before = baseline_brief.get("recommendation", "")
    rec_after = intervention_brief.get("recommendation", "")
    recommendation_change = (
        {"before": rec_before, "after": rec_after}
        if rec_before != rec_after
        else None
    )

    # --- support_change (agreement_score delta) ---
    score_before = _safe_float(baseline_brief.get("agreement_score"))
    score_after = _safe_float(intervention_brief.get("agreement_score"))
    support_change = round(score_after - score_before, 4)

    # --- concerns ---
    baseline_concerns = _extract_text_set(
        baseline_brief.get("critical_unknowns", []), "question",
    )
    intervention_concerns = _extract_text_set(
        intervention_brief.get("critical_unknowns", []), "question",
    )
    new_concerns = sorted(intervention_concerns - baseline_concerns)
    resolved_concerns = sorted(baseline_concerns - intervention_concerns)

    # --- guardrail status changes ---
    baseline_guardrails = {
        g["condition"]: g.get("status", "")
        for g in baseline_brief.get("guardrails", [])
        if isinstance(g, dict) and g.get("condition")
    }
    intervention_guardrails = {
        g["condition"]: g.get("status", "")
        for g in intervention_brief.get("guardrails", [])
        if isinstance(g, dict) and g.get("condition")
    }
    guardrail_changes = []
    for condition in sorted(set(baseline_guardrails) | set(intervention_guardrails)):
        old_status = baseline_guardrails.get(condition)
        new_status = intervention_guardrails.get(condition)
        if old_status != new_status:
            guardrail_changes.append({
                "condition": condition,
                "before": old_status,
                "after": new_status,
            })

    # --- key_differences (top 3) ---
    key_differences: list[str] = []
    if recommendation_change:
        key_differences.append(
            f"推奨が {rec_before} から {rec_after} に変化"
        )
    if support_change != 0.0:
        direction = "上昇" if support_change > 0 else "低下"
        key_differences.append(
            f"支持スコアが {abs(support_change) * 100:.1f}% {direction}"
        )
    if new_concerns:
        key_differences.append(
            f"新たな懸念が {len(new_concerns)} 件出現: {', '.join(new_concerns[:2])}"
        )
    if resolved_concerns and len(key_differences) < 3:
        key_differences.append(
            f"解消された懸念が {len(resolved_concerns)} 件: {', '.join(resolved_concerns[:2])}"
        )
    if guardrail_changes and len(key_differences) < 3:
        key_differences.append(
            f"ガードレール {len(guardrail_changes)} 件のステータスが変化"
        )
    # --- key_reasons diff ---
    baseline_reasons = _extract_text_set(
        baseline_brief.get("key_reasons", []), "reason",
    )
    intervention_reasons = _extract_text_set(
        intervention_brief.get("key_reasons", []), "reason",
    )
    new_reasons = intervention_reasons - baseline_reasons
    if new_reasons and len(key_differences) < 3:
        key_differences.append(
            f"新たな判断根拠が {len(new_reasons)} 件追加"
        )

    key_differences = key_differences[:3]

    return {
        "recommendation_change": recommendation_change,
        "support_change": support_change,
        "new_concerns": new_concerns,
        "resolved_concerns": resolved_concerns,
        "guardrail_changes": guardrail_changes,
        "coalition_shifts": [],  # populated by build_scenario_comparison
        "key_differences": key_differences,
    }


def _compute_shift_magnitude(event: dict) -> float:
    """Compute the magnitude of opinion shift from an audit event dict."""
    before = event.get("before_state", {})
    after = event.get("after_state", {})
    # Try common keys: stance, support, confidence
    for key in ("stance", "support", "confidence", "score"):
        b = _safe_float(before.get(key))
        a = _safe_float(after.get(key))
        if b != 0.0 or a != 0.0:
            return abs(a - b)
    # Fallback: count how many keys changed
    all_keys = set(before.keys()) | set(after.keys())
    changed = sum(1 for k in all_keys if before.get(k) != after.get(k))
    return float(changed)


def extract_opinion_shifts_top5(audit_events: list[dict]) -> list[dict]:
    """Extract the top 5 agents with the largest opinion shifts.

    Each audit_event dict should have:
      agent_id, agent_name, before_state, after_state, reasoning (optional)

    Returns list of dicts sorted by shift magnitude (descending), max 5.
    """
    scored: list[tuple[float, dict]] = []
    for event in audit_events:
        magnitude = _compute_shift_magnitude(event)
        scored.append((magnitude, {
            "agent_id": event.get("agent_id", ""),
            "agent_name": event.get("agent_name", ""),
            "shift_magnitude": round(magnitude, 4),
            "before_state": event.get("before_state", {}),
            "after_state": event.get("after_state", {}),
            "reasoning": event.get("reasoning", ""),
        }))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:5]]


def build_coalition_map(agents: list[dict], audit_events: list | None = None) -> dict:
    """Build a group-level breakdown of support/opposition.

    Groups agents by: age_bracket, region, occupation, primary_value.
    For each group: calculate support %, opposition %, count.

    An agent is "supporting" if stance >= 0.5, "opposing" otherwise.
    The stance is read from agent["stance"] (float 0-1).

    Args:
        agents: list of agent dicts with demographics + stance.
        audit_events: optional audit events (reserved for future enrichment).

    Returns:
        {
            "by_age": [{"group": "18-29", "support": 0.7, "oppose": 0.3, "count": 30}, ...],
            "by_region": [...],
            "by_occupation": [...],
            "by_value": [...],
        }
    """
    if not agents:
        return {
            "by_age": [],
            "by_region": [],
            "by_occupation": [],
            "by_value": [],
        }

    grouping_keys = {
        "by_age": "age_bracket",
        "by_region": "region",
        "by_occupation": "occupation",
        "by_value": "primary_value",
    }
    result: dict[str, list[dict]] = {}

    for label, agent_key in grouping_keys.items():
        buckets: dict[str, dict] = {}  # group_name -> {support: int, total: int}
        for agent in agents:
            group_name = agent.get(agent_key) or "不明"
            if group_name not in buckets:
                buckets[group_name] = {"support": 0, "total": 0}
            buckets[group_name]["total"] += 1
            stance = _safe_float(agent.get("stance"), 0.5)
            if stance >= 0.5:
                buckets[group_name]["support"] += 1
        group_list = []
        for group_name in sorted(buckets.keys()):
            data = buckets[group_name]
            total = data["total"]
            support_ratio = round(data["support"] / total, 4) if total else 0.0
            group_list.append({
                "group": group_name,
                "support": support_ratio,
                "oppose": round(1.0 - support_ratio, 4),
                "count": total,
            })
        result[label] = group_list

    return result


# ---------------------------------------------------------------------------
# Async orchestrator (DB calls)
# ---------------------------------------------------------------------------


async def build_scenario_comparison(
    session: AsyncSession,
    scenario_pair_id: str,
) -> dict:
    """Build a comparison between baseline and intervention scenarios.

    Fetches the ScenarioPair, builds decision briefs for both simulations,
    computes the delta, and assembles opinion shifts and coalition map.

    Returns:
    {
        "scenario_pair_id": str,
        "baseline_brief": dict,
        "intervention_brief": dict,
        "delta": dict,
        "opinion_shifts_top5": list[dict],
        "coalition_map": dict,
    }
    """
    pair = await session.get(ScenarioPair, scenario_pair_id)
    if pair is None:
        raise ValueError(f"ScenarioPair not found: {scenario_pair_id}")

    # Fetch simulations
    from src.app.models.simulation import Simulation

    baseline_sim = await session.get(Simulation, pair.baseline_simulation_id)
    intervention_sim = await session.get(Simulation, pair.intervention_simulation_id)
    if baseline_sim is None or intervention_sim is None:
        raise ValueError(
            f"One or both simulations missing for pair {scenario_pair_id}"
        )

    # Build decision briefs from simulation metadata
    baseline_brief = build_single_decision_brief(
        prompt_text=baseline_sim.prompt_text,
        report_content=baseline_sim.metadata_json.get("report_content", ""),
        sections=baseline_sim.metadata_json.get("sections"),
        quality=baseline_sim.metadata_json.get("quality"),
    )
    intervention_brief = build_single_decision_brief(
        prompt_text=intervention_sim.prompt_text,
        report_content=intervention_sim.metadata_json.get("report_content", ""),
        sections=intervention_sim.metadata_json.get("sections"),
        quality=intervention_sim.metadata_json.get("quality"),
    )

    # Delta
    delta = build_delta_brief(baseline_brief, intervention_brief)

    # Opinion shifts from audit trail
    baseline_shifts = await get_opinion_shifts(session, str(baseline_sim.id))
    intervention_shifts = await get_opinion_shifts(session, str(intervention_sim.id))

    all_shift_dicts = [
        {
            "agent_id": e.agent_id,
            "agent_name": e.agent_name,
            "before_state": e.before_state,
            "after_state": e.after_state,
            "reasoning": e.reasoning,
        }
        for e in intervention_shifts
    ]
    opinion_shifts_top5 = extract_opinion_shifts_top5(all_shift_dicts)

    # Coalition map from agents in metadata (if available)
    agents = intervention_sim.metadata_json.get("agents", [])
    coalition_map = build_coalition_map(agents, all_shift_dicts)

    # Enrich delta with coalition shifts (compare baseline vs intervention groups)
    baseline_agents = baseline_sim.metadata_json.get("agents", [])
    if baseline_agents and agents:
        baseline_coalition = build_coalition_map(baseline_agents)
        coalition_shifts = _compute_coalition_shifts(baseline_coalition, coalition_map)
        delta["coalition_shifts"] = coalition_shifts

    return {
        "scenario_pair_id": scenario_pair_id,
        "baseline_brief": baseline_brief,
        "intervention_brief": intervention_brief,
        "delta": delta,
        "opinion_shifts_top5": opinion_shifts_top5,
        "coalition_map": coalition_map,
    }


def _compute_coalition_shifts(
    baseline_map: dict, intervention_map: dict,
) -> list[dict]:
    """Compare two coalition maps and find groups that shifted position."""
    shifts: list[dict] = []
    for dimension in ("by_age", "by_region", "by_occupation", "by_value"):
        baseline_groups = {
            g["group"]: g for g in baseline_map.get(dimension, [])
        }
        intervention_groups = {
            g["group"]: g for g in intervention_map.get(dimension, [])
        }
        all_groups = sorted(set(baseline_groups) | set(intervention_groups))
        for group_name in all_groups:
            b = baseline_groups.get(group_name, {})
            i = intervention_groups.get(group_name, {})
            b_support = _safe_float(b.get("support"))
            i_support = _safe_float(i.get("support"))
            change = round(i_support - b_support, 4)
            if abs(change) >= 0.05:  # threshold: 5% shift
                shifts.append({
                    "dimension": dimension,
                    "group": group_name,
                    "baseline_support": b_support,
                    "intervention_support": i_support,
                    "change": change,
                })
    return shifts
