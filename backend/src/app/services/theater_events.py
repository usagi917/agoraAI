"""Theater Events: SSE event extraction and emission for debate visualization.

Emits five event types:
  - claim_made: When an agent makes a new claim during debate
  - stance_shifted: When an agent's stance changes between rounds
  - alliance_formed: When 2+ agents converge on the same stance
  - market_moved: When prediction market probability shifts 5%+
  - decision_locked: When final consensus is reached
"""

import logging
from typing import Any

from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

# --- Stance value mapping ---

_STANCE_VALUES: dict[str, float] = {
    "賛成": 1.0,
    "条件付き賛成": 0.7,
    "中立": 0.5,
    "条件付き反対": 0.3,
    "反対": 0.0,
}


def stance_to_numeric(stance: str) -> float:
    """Convert a Japanese stance label to a numeric value in [0, 1].

    Falls back to 0.5 for unknown stances.
    """
    if stance in _STANCE_VALUES:
        return _STANCE_VALUES[stance]
    # Try partial matching (only non-empty strings)
    if stance:
        for key, val in _STANCE_VALUES.items():
            if key in stance or stance in key:
                return val
    return 0.5


# --- 1. claim_made ---

async def emit_claim_made(
    run_id: str,
    agent_id: int | str,
    claim_text: str,
    stance: str,
    confidence: float,
) -> None:
    """Emit a claim_made event when an agent makes a new claim."""
    await sse_manager.publish(run_id, "claim_made", {
        "agent_id": agent_id,
        "claim_text": claim_text,
        "stance": stance,
        "confidence": round(confidence, 4),
    })


async def emit_claims_from_round(
    run_id: str,
    round_arguments: list[dict],
) -> None:
    """Extract and emit claim_made events from a round's arguments."""
    for arg in round_arguments:
        agent_id = arg.get("participant_index", -1)
        claim_text = (arg.get("argument") or "").strip()
        stance = arg.get("position", "")
        # confidence from the original agent response, default 0.5
        confidence = 0.5
        if not claim_text:
            continue
        await emit_claim_made(run_id, agent_id, claim_text[:500], stance, confidence)


# --- 2. stance_shifted ---

async def emit_stance_shifted(
    run_id: str,
    agent_id: int | str,
    from_stance: float,
    to_stance: float,
    reason: str,
) -> None:
    """Emit a stance_shifted event."""
    await sse_manager.publish(run_id, "stance_shifted", {
        "agent_id": agent_id,
        "from_stance": round(from_stance, 4),
        "to_stance": round(to_stance, 4),
        "reason": reason,
    })


async def detect_and_emit_stance_shifts(
    run_id: str,
    prev_round: list[dict],
    curr_round: list[dict],
    threshold: float = 0.1,
) -> list[dict]:
    """Compare stance values between rounds and emit stance_shifted for deltas >= threshold.

    Returns list of shift records for downstream use.
    """
    # Build previous stance map: participant_index -> position
    prev_stances: dict[int | str, str] = {}
    for arg in prev_round:
        pid = arg.get("participant_index", -1)
        pos = arg.get("position", "")
        if pid != -1 and pos:
            prev_stances[pid] = pos

    shifts: list[dict] = []
    for arg in curr_round:
        pid = arg.get("participant_index", -1)
        pos = arg.get("position", "")
        if pid == -1 or not pos or pid not in prev_stances:
            continue

        old_val = stance_to_numeric(prev_stances[pid])
        new_val = stance_to_numeric(pos)
        delta = abs(new_val - old_val)

        if delta >= threshold:
            reason = (arg.get("belief_update") or "").strip() or "stance changed"
            await emit_stance_shifted(run_id, pid, old_val, new_val, reason)
            shifts.append({
                "agent_id": pid,
                "from_stance": old_val,
                "to_stance": new_val,
                "reason": reason,
            })

    return shifts


# --- 3. alliance_formed ---

async def emit_alliance_formed(
    run_id: str,
    agent_ids: list[int | str],
    stance: float,
    strength: float,
) -> None:
    """Emit an alliance_formed event."""
    await sse_manager.publish(run_id, "alliance_formed", {
        "agent_ids": agent_ids,
        "stance": round(stance, 4),
        "strength": round(strength, 4),
    })


async def detect_and_emit_alliances(
    run_id: str,
    round_arguments: list[dict],
    proximity_threshold: float = 0.15,
) -> list[dict]:
    """Detect stance clusters and emit alliance_formed events.

    Algorithm:
      1. Sort agents by numeric stance value.
      2. Walk through sorted list, grouping adjacent agents with delta < proximity_threshold.
      3. Fire event for groups of size >= 2.
      4. Cap each coalition at 50% of total agents.

    Returns list of alliance records.
    """
    # Collect unique agents (skip duplicates from sub-rounds)
    agent_stances: dict[int | str, tuple[float, str]] = {}
    for arg in round_arguments:
        pid = arg.get("participant_index", -1)
        pos = arg.get("position", "")
        if pid == -1:
            continue
        # Last occurrence wins (for sub_round updates)
        agent_stances[pid] = (stance_to_numeric(pos), pos)

    if len(agent_stances) < 2:
        return []

    total_agents = len(agent_stances)
    max_coalition = total_agents // 2 if total_agents > 2 else total_agents

    # Sort by stance value
    sorted_agents = sorted(agent_stances.items(), key=lambda x: x[1][0])

    alliances: list[dict] = []
    cluster: list[int | str] = [sorted_agents[0][0]]
    cluster_values: list[float] = [sorted_agents[0][1][0]]

    for i in range(1, len(sorted_agents)):
        pid, (val, _pos) = sorted_agents[i]
        if val - cluster_values[-1] < proximity_threshold:
            cluster.append(pid)
            cluster_values.append(val)
        else:
            # Flush previous cluster
            if len(cluster) >= 2:
                capped = cluster[:max_coalition]
                capped_vals = cluster_values[:max_coalition]
                avg_stance = sum(capped_vals) / len(capped_vals)
                strength = len(capped) / total_agents
                alliances.append({
                    "agent_ids": list(capped),
                    "stance": avg_stance,
                    "strength": strength,
                })
            cluster = [pid]
            cluster_values = [val]

    # Flush last cluster
    if len(cluster) >= 2:
        capped = cluster[:max_coalition]
        capped_vals = cluster_values[:max_coalition]
        avg_stance = sum(capped_vals) / len(capped_vals)
        strength = len(capped) / total_agents
        alliances.append({
            "agent_ids": list(capped),
            "stance": avg_stance,
            "strength": strength,
        })

    for alliance in alliances:
        await emit_alliance_formed(
            run_id,
            alliance["agent_ids"],
            alliance["stance"],
            alliance["strength"],
        )

    return alliances


# --- 4. market_moved ---

async def emit_market_moved(
    run_id: str,
    market_id: str,
    old_prob: float,
    new_prob: float,
    driver: str,
) -> None:
    """Emit a market_moved event when prediction market probability shifts 5%+."""
    await sse_manager.publish(run_id, "market_moved", {
        "market_id": market_id,
        "old_prob": round(old_prob, 4),
        "new_prob": round(new_prob, 4),
        "driver": driver,
    })


async def detect_and_emit_market_move(
    run_id: str,
    market_id: str,
    old_prob: float,
    new_prob: float,
    driver: str = "",
    threshold: float = 0.05,
) -> bool:
    """Check if market probability delta exceeds threshold and emit if so.

    Returns True if event was emitted.
    """
    if abs(new_prob - old_prob) >= threshold:
        await emit_market_moved(run_id, market_id, old_prob, new_prob, driver)
        return True
    return False


# --- 5. decision_locked ---

async def emit_decision_locked(
    run_id: str,
    decision_text: str,
    confidence: float,
    dissent_count: int,
) -> None:
    """Emit a decision_locked event when final consensus is reached."""
    await sse_manager.publish(run_id, "decision_locked", {
        "decision_text": decision_text,
        "confidence": round(confidence, 4),
        "dissent_count": dissent_count,
    })


async def emit_decision_from_synthesis(
    run_id: str,
    decision_brief: dict,
    agreement_score: float,
) -> None:
    """Extract and emit decision_locked from a synthesis result."""
    decision_text = (
        decision_brief.get("decision_summary", "")
        or decision_brief.get("recommendation", "")
        or ""
    )
    confidence = agreement_score
    dissent_count = len(decision_brief.get("disagreement_points", []) or [])

    if decision_text:
        await emit_decision_locked(run_id, decision_text[:500], confidence, dissent_count)


# --- Integration hooks ---

async def process_round_theater_events(
    run_id: str,
    round_arguments: list[dict],
    prev_round: list[dict] | None = None,
) -> None:
    """Hook to call after each meeting round to emit theater events.

    Emits claim_made, stance_shifted (if prev_round), and alliance_formed events.
    """
    # 1. Emit claims
    await emit_claims_from_round(run_id, round_arguments)

    # 2. Detect stance shifts (requires previous round)
    if prev_round:
        await detect_and_emit_stance_shifts(run_id, prev_round, round_arguments)

    # 3. Detect alliances
    await detect_and_emit_alliances(run_id, round_arguments)
