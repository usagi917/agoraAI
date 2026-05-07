"""Wondrous Crayon 統合層: t0..t5 時系列予測を 1 関数で実行する.

society_orchestrator の末尾フックから呼ばれる pure 関数 wrapper。
新規モジュール (cascade_propagator, particle_filter, internal_observation_loop,
time_axis_orchestrator, temporal_report_generator) を組み合わせて、
LLM を追加で呼ばずに t0..t5 の時系列予測 + 統合レポートを返す。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from src.app.services.communication.cascade_propagator import CascadePropagator
from src.app.services.society.internal_observation_loop import (
    integrate_cascade_with_belief,
)
from src.app.services.society.particle_filter import ParticleFilter
from src.app.services.society.temporal_report_generator import TemporalReportGenerator
from src.app.services.society.time_axis_orchestrator import (
    DEFAULT_HORIZONS,
    TimeAxisOrchestrator,
    TimeStep,
    TimeStepSnapshot,
)

logger = logging.getLogger(__name__)

STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


class SSEPublisher(Protocol):
    async def publish(self, run_id: str, event_type: str, payload: dict) -> None: ...


def _normalize_responses(responses: list[dict]) -> list[dict]:
    """cascade_propagator が期待する形式に揃える (agent_id, stance, confidence)."""
    normalized: list[dict] = []
    for idx, r in enumerate(responses):
        agent_id = r.get("agent_id", idx)
        stance = r.get("stance", "中立")
        confidence = float(r.get("confidence", 0.5))
        normalized.append({
            "agent_id": agent_id,
            "stance": stance,
            "confidence": confidence,
        })
    return normalized


async def run_time_axis_pipeline(
    simulation_id: str,
    base_responses: list[dict],
    base_edges: list[tuple[Any, Any]],
    theme: str,
    sse_manager: SSEPublisher | None = None,
    num_cascade_rounds: int = 5,
    n_particles: int = 32,
) -> dict[str, Any]:
    """t0..t5 の時系列予測を実行し、統合レポート dict を返す.

    各 step で:
      1. cascade_propagator で N ラウンド会話伝播
      2. internal_observation_loop で粒子フィルタ更新
      3. 集約分布を snapshot に保存
      4. SSE で進捗配信
    """
    initial_responses = _normalize_responses(base_responses)
    initial_edges = [tuple(e) for e in base_edges]

    cascade = CascadePropagator(num_rounds=num_cascade_rounds)

    async def step_fn(step: TimeStep, state: dict[str, Any]) -> TimeStepSnapshot:
        if sse_manager is not None:
            await sse_manager.publish(simulation_id, "time_step_started", {
                "key": step.key,
                "label": step.label,
                "delta_days": step.delta_days,
                "t_index": step.t_index,
            })

        responses = state.get("responses", [])
        edges = state.get("edges", [])

        if not responses:
            distribution = {s: 1 / len(STANCES) for s in STANCES}
            new_state = {"responses": [], "edges": edges}
            snapshot = TimeStepSnapshot(
                step=step,
                state=new_state,
                distribution=distribution,
                metadata={"empty": True},
            )
        else:
            cascade_snapshots = cascade.propagate(
                initial_responses=responses,
                graph_edges=edges,
            )
            pf = ParticleFilter(
                n_particles=n_particles,
                stances=STANCES,
                seed=step.t_index,
            )
            distribution = integrate_cascade_with_belief(cascade_snapshots, pf)

            # 次 step に引き継ぐ state: cascade 最終ラウンドの応答 + 同じグラフ
            next_responses = cascade_snapshots[-1] if cascade_snapshots else responses
            new_state = {
                "responses": next_responses,
                "edges": edges,
            }
            snapshot = TimeStepSnapshot(
                step=step,
                state=new_state,
                distribution=distribution,
            )

        if sse_manager is not None:
            await sse_manager.publish(simulation_id, "time_step_completed", {
                "key": step.key,
                "label": step.label,
                "distribution": snapshot.distribution,
            })

        return snapshot

    initial_state = {"responses": initial_responses, "edges": initial_edges}
    orchestrator = TimeAxisOrchestrator(horizons=DEFAULT_HORIZONS)
    snapshots = await orchestrator.run(initial_state=initial_state, step_fn=step_fn)

    report = TemporalReportGenerator().generate(snapshots=snapshots, theme=theme)

    if sse_manager is not None:
        await sse_manager.publish(simulation_id, "time_axis_completed", {
            "horizons": len(snapshots),
            "theme": theme,
        })

    return report
