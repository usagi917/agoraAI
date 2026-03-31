"""Network Propagation: multi-round opinion dynamics with optional LLM reflection.

Orchestrates the OpinionDynamicsEngine over multiple timesteps, converting
between the activation layer's stance/confidence format and the engine's
numerical opinion vectors.

LLM reflection is only triggered for agents whose opinion shifts exceed a
threshold, keeping costs controlled (~10 calls per round).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from src.app.services.society.opinion_dynamics import (
    ClusterInfo,
    OpinionDynamicsEngine,
    stubbornness_from_big_five,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stance <-> Opinion conversion
# ---------------------------------------------------------------------------

_STANCE_TO_BASE: dict[str, float] = {
    "賛成": 0.9,
    "条件付き賛成": 0.7,
    "中立": 0.5,
    "条件付き反対": 0.3,
    "反対": 0.1,
}

_STANCE_THRESHOLDS: list[tuple[float, str]] = [
    (0.8, "賛成"),
    (0.6, "条件付き賛成"),
    (0.4, "中立"),
    (0.2, "条件付き反対"),
    (0.0, "反対"),
]


def _convert_stance_to_opinion(stance: str, confidence: float) -> list[float]:
    """Convert stance label + confidence to 1D opinion vector."""
    base = _STANCE_TO_BASE.get(stance, 0.5)
    # Modulate: high confidence pushes toward extremes, low confidence toward center
    opinion = 0.5 + (base - 0.5) * confidence
    return [round(opinion, 4)]


def _convert_opinion_to_stance(opinion: list[float]) -> str:
    """Convert 1D opinion vector back to stance label."""
    val = opinion[0]
    for threshold, label in _STANCE_THRESHOLDS:
        if val >= threshold:
            return label
    return "反対"


def _should_trigger_reflection(
    old_opinion: list[float],
    new_opinion: list[float],
    threshold: float = 0.3,
) -> bool:
    """Check if opinion shift is large enough to trigger LLM reflection."""
    delta = np.linalg.norm(
        np.array(new_opinion) - np.array(old_opinion),
    )
    return bool(delta > threshold)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TimestepRecord:
    timestep: int
    opinions: list[list[float]]
    opinion_distribution: dict[str, float]
    entropy: float
    cluster_count: int
    max_delta: float


@dataclass
class PropagationResult:
    final_opinions: list[list[float]]
    timestep_history: list[TimestepRecord]
    clusters: list[ClusterInfo]
    converged: bool
    total_timesteps: int
    metrics: dict[str, Any] = field(default_factory=dict)
    reflection_count: int = 0
    reflections: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM Reflection
# ---------------------------------------------------------------------------

def _build_reflection_prompt(
    agent: dict,
    old_opinion: list[float],
    new_opinion: list[float],
    neighbor_opinions: list[dict],
    theme: str,
) -> tuple[str, str]:
    """Build a prompt for an agent to explain why their opinion shifted.

    Args:
        agent: Agent profile dict with demographics, values, speech_style, etc.
        old_opinion: Opinion vector before the shift.
        new_opinion: Opinion vector after the shift.
        neighbor_opinions: List of dicts with agent_id, opinion, reason.
        theme: Discussion topic.

    Returns:
        (system_prompt, user_prompt) tuple.
    """
    demographics = agent.get("demographics", {})
    age = demographics.get("age", "不明")
    occupation = demographics.get("occupation", "不明")
    region = demographics.get("region", "不明")
    speech_style = agent.get("speech_style", "自然")

    values = agent.get("values", {})
    top_values = sorted(values.items(), key=lambda x: x[1], reverse=True)[:3]
    values_str = "、".join(v[0] for v in top_values) if top_values else "特になし"

    old_stance = _convert_opinion_to_stance(old_opinion)
    new_stance = _convert_opinion_to_stance(new_opinion)

    system_prompt = (
        f"あなたは{region}に住む{age}歳の{occupation}です。\n"
        f"話し方: {speech_style}\n"
        f"重視する価値観: {values_str}\n"
        f"テーマ「{theme}」について、あなたの意見が変化した理由を振り返ってください。"
    )

    neighbor_quotes = []
    for n in neighbor_opinions:
        reason = n.get("reason", "")
        n_opinion = n.get("opinion", [0.5])
        n_stance = _convert_opinion_to_stance(n_opinion)
        if reason:
            neighbor_quotes.append(f"- {n_stance}の人: 「{reason}」")
        else:
            neighbor_quotes.append(f"- {n_stance}の人の意見")
    neighbor_text = "\n".join(neighbor_quotes) if neighbor_quotes else "（近隣の意見なし）"

    user_prompt = (
        f"テーマ: {theme}\n\n"
        f"あなたの元のスタンス: {old_stance}（数値: {old_opinion[0]:.2f}）\n"
        f"変化後のスタンス: {new_stance}（数値: {new_opinion[0]:.2f}）\n\n"
        f"あなたの周囲の人々の意見:\n{neighbor_text}\n\n"
        f"なぜあなたの意見が変わったのか、100〜200文字で説明してください。"
        f"自分の生活実感に基づいて、周囲のどの意見に影響されたかを述べてください。"
    )

    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Echo chamber metrics
# ---------------------------------------------------------------------------

def _compute_echo_chamber_metrics(
    agents_with_opinions: list[dict],
    edges: list[dict],
) -> dict[str, Any]:
    """Compute echo chamber / homophily metrics."""
    if not edges:
        return {"homophily_index": 0.0, "polarization_index": 0.0}

    # Build opinion lookup
    opinion_map: dict[str, float] = {}
    for a in agents_with_opinions:
        opinion_map[a["id"]] = a["opinion"][0]

    # Homophily: fraction of edges connecting agents with similar stance
    same_stance_count = 0
    total_edges = 0
    for e in edges:
        src_op = opinion_map.get(e["agent_id"])
        tgt_op = opinion_map.get(e["target_id"])
        if src_op is not None and tgt_op is not None:
            total_edges += 1
            src_stance = _convert_opinion_to_stance([src_op])
            tgt_stance = _convert_opinion_to_stance([tgt_op])
            if src_stance == tgt_stance:
                same_stance_count += 1

    homophily = same_stance_count / total_edges if total_edges > 0 else 0.0

    # Polarization: bimodality of opinion distribution
    opinions = list(opinion_map.values())
    if len(opinions) < 2:
        polarization = 0.0
    else:
        variance = float(np.var(opinions))
        # Normalize: max variance for uniform [0,1] is 1/12 ≈ 0.083
        polarization = min(variance / 0.083, 1.0)

    return {
        "homophily_index": round(homophily, 4),
        "polarization_index": round(polarization, 4),
    }


def _compute_stance_distribution(opinions: list[list[float]]) -> dict[str, float]:
    """Compute stance distribution from opinion vectors."""
    if not opinions:
        return {}
    stances: dict[str, int] = {}
    for op in opinions:
        stance = _convert_opinion_to_stance(op)
        stances[stance] = stances.get(stance, 0) + 1
    total = len(opinions)
    return {k: round(v / total, 4) for k, v in stances.items()}


def _shannon_entropy(distribution: dict[str, float]) -> float:
    """Shannon entropy of a probability distribution."""
    probs = [p for p in distribution.values() if p > 0]
    if not probs:
        return 0.0
    return float(-sum(p * np.log2(p) for p in probs))


# ---------------------------------------------------------------------------
# Main propagation function
# ---------------------------------------------------------------------------

async def run_network_propagation(
    agents: list[dict],
    initial_responses: list[dict],
    edges: list[dict],
    theme: str,
    max_timesteps: int = 20,
    convergence_threshold: float = 0.01,
    confidence_threshold: float = 0.3,
    reflection_delta_threshold: float = 0.3,
    on_timestep: Callable | None = None,
    llm_client: Any | None = None,
) -> PropagationResult:
    """Run multi-round network opinion propagation.

    Args:
        agents: Agent profile dicts (must have id, big_five).
        initial_responses: Activation responses with stance/confidence.
        edges: SocialEdge dicts with agent_id, target_id, strength.
        theme: Discussion topic.
        max_timesteps: Maximum propagation rounds.
        convergence_threshold: Epsilon for convergence detection.
        confidence_threshold: Bounded confidence threshold (Hegselmann-Krause).
        reflection_delta_threshold: Opinion shift threshold for LLM reflection.
        on_timestep: Optional callback per timestep.
        llm_client: Optional LLM client (e.g. MultiLLMClient) for reflection.
            If None, reflection is skipped (pure math only).

    Returns:
        PropagationResult with final opinions, history, clusters, and metrics.
    """
    # Build response lookup
    response_map: dict[str, dict] = {}
    for r in initial_responses:
        response_map[r["agent_id"]] = r

    # Convert to opinion dynamics format
    engine_agents = []
    for agent in agents:
        agent_id = agent["id"]
        resp = response_map.get(agent_id, {})
        stance = resp.get("stance", "中立")
        confidence = resp.get("confidence", 0.5)
        big_five_c = agent.get("big_five", {}).get("C", 0.5)

        opinion = _convert_stance_to_opinion(stance, confidence)
        stubbornness = stubbornness_from_big_five(big_five_c)

        engine_agents.append({
            "id": agent_id,
            "opinion_vector": opinion,
            "stubbornness": stubbornness,
        })

    # Initialize engine
    engine = OpinionDynamicsEngine(
        agents=engine_agents,
        edges=edges,
        confidence_threshold=confidence_threshold,
    )

    # Run propagation
    timestep_history: list[TimestepRecord] = []
    total_reflections = 0
    reflections: list[dict[str, Any]] = []

    # Store initial opinions for later reflection comparison
    initial_opinions = [ea["opinion_vector"][:] for ea in engine_agents]

    for t in range(max_timesteps):
        prev_opinions = [ea["opinion_vector"] for ea in engine_agents] if t == 0 else [
            list(row) for row in engine._opinions
        ]

        result = engine.propagation_step(timestep=t)

        # Record timestep
        dist = _compute_stance_distribution(result.updated_opinions)
        entropy = _shannon_entropy(dist)
        clusters = engine.detect_clusters()

        record = TimestepRecord(
            timestep=t,
            opinions=[list(row) for row in result.updated_opinions],
            opinion_distribution=dist,
            entropy=entropy,
            cluster_count=len(clusters),
            max_delta=result.max_delta,
        )
        timestep_history.append(record)

        if on_timestep:
            if inspect.iscoroutinefunction(on_timestep):
                await on_timestep(record)
            else:
                on_timestep(record)

        # Check convergence
        if engine.detect_convergence(window=3, epsilon=convergence_threshold):
            logger.info("Network propagation converged at timestep %d", t)
            break

    # Final state
    final_opinions = [list(row) for row in engine._opinions]
    final_clusters = engine.detect_clusters()
    converged = engine.detect_convergence(window=3, epsilon=convergence_threshold)
    total_ts = len(timestep_history)

    # --- LLM Reflection for agents with large opinion shifts ---
    if llm_client is not None:
        # Build neighbor lookup from edges
        neighbor_map: dict[str, list[str]] = {}
        for e in edges:
            src = e["agent_id"]
            tgt = e["target_id"]
            neighbor_map.setdefault(src, []).append(tgt)

        agent_id_to_idx: dict[str, int] = {
            agents[i]["id"]: i for i in range(len(agents))
        }

        reflection_tasks = []
        for i, agent in enumerate(agents):
            old_op = initial_opinions[i]
            new_op = final_opinions[i]
            if _should_trigger_reflection(old_op, new_op, threshold=reflection_delta_threshold):
                # Gather neighbor opinions and reasons
                agent_id = agent["id"]
                neighbor_ids = neighbor_map.get(agent_id, [])
                neighbor_opinions = []
                for nid in neighbor_ids[:5]:  # limit to top 5 neighbors
                    n_idx = agent_id_to_idx.get(nid)
                    if n_idx is not None:
                        n_resp = response_map.get(nid, {})
                        neighbor_opinions.append({
                            "agent_id": nid,
                            "opinion": final_opinions[n_idx],
                            "reason": n_resp.get("reason", ""),
                        })

                reflection_tasks.append((i, agent, old_op, new_op, neighbor_opinions))

        # Run reflections concurrently
        async def _reflect(
            idx: int, agent: dict, old_op: list[float],
            new_op: list[float], neighbors: list[dict],
        ) -> dict[str, Any]:
            system_prompt, user_prompt = _build_reflection_prompt(
                agent, old_op, new_op, neighbors, theme,
            )
            try:
                result_text, _usage = await llm_client.call(
                    provider_name=agent.get("llm_backend", "openai"),
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.5,
                    max_tokens=256,
                )
                text = result_text if isinstance(result_text, str) else str(result_text)
            except Exception as exc:
                logger.warning("Reflection failed for agent %s: %s", agent["id"], exc)
                text = ""

            return {
                "agent_id": agent["id"],
                "old_stance": _convert_opinion_to_stance(old_op),
                "new_stance": _convert_opinion_to_stance(new_op),
                "reflection_text": text,
            }

        if reflection_tasks:
            reflection_results = await asyncio.gather(
                *[_reflect(idx, ag, old, new, nb) for idx, ag, old, new, nb in reflection_tasks]
            )
            reflections = list(reflection_results)
            total_reflections = len(reflections)
            logger.info("LLM reflections generated: %d agents", total_reflections)

    # Echo chamber metrics
    agents_with_opinions = [
        {"id": agents[i]["id"], "opinion": final_opinions[i]}
        for i in range(len(agents))
    ]
    echo_metrics = _compute_echo_chamber_metrics(agents_with_opinions, edges)

    return PropagationResult(
        final_opinions=final_opinions,
        timestep_history=timestep_history,
        clusters=final_clusters,
        converged=converged,
        total_timesteps=total_ts,
        metrics={"echo_chamber": echo_metrics},
        reflection_count=total_reflections,
        reflections=reflections,
    )
