"""全人口意見伝播: 選抜エージェントの LLM 回答を種として大衆へ広げる。

活性化済み（LLM 回答あり）のエージェントは stance×confidence の意見と
Big Five 由来の頑固さでアンカーされ、未活性化の大衆は中立 (0.5) から
スタートし頑固さが減衰されて周囲に感化されやすい。

OpinionDynamicsEngine（Hegselmann-Krause + Friedkin-Johnsen）を直接駆動し、
ラウンドごとのスタンス変化デルタをコールバックで通知する（SSE 配信用）。
クラスタ検出（DBSCAN）は 10k 規模ではラウンド毎に重いため行わない。
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.app.services.society.accuracy_config import is_enabled
from src.app.services.society.network_propagation import (
    _convert_opinion_to_stance,
    _convert_stance_to_opinion,
)
from src.app.services.society.opinion_dynamics import (
    OpinionDynamicsEngine,
    compute_filter_bubble_thresholds,
    compute_heterogeneous_thresholds,
    stubbornness_from_big_five,
)

logger = logging.getLogger(__name__)

#: 未活性化エージェントの頑固さ減衰率（意見をまだ持たない人は感化されやすい）
SUSCEPTIBILITY_DAMPENING = 0.6

#: 減衰後の頑固さ下限
MIN_SUSCEPTIBLE_STUBBORNNESS = 0.2

#: 収束判定の窓幅と閾値
_CONVERGENCE_WINDOW = 2
_CONVERGENCE_EPSILON = 0.005


@dataclass
class PropagationRoundDelta:
    """1 ラウンド分のスタンス変化。SSE 配信用のコンパクトな差分。"""

    round: int
    changes: list[dict]  # {"agent_index": int, "agent_id": str, "stance": str, "opinion": float}
    changed_count: int
    distribution: dict[str, float]
    max_delta: float


@dataclass
class PopulationPropagationResult:
    final_stances: list[dict]  # {"agent_id", "agent_index", "stance", "opinion"}
    distribution: dict[str, float]
    total_rounds: int
    converged: bool
    rounds: list[PropagationRoundDelta] = field(default_factory=list)


def _mirror_edges(edges: list[dict]) -> list[dict]:
    """無向ソーシャルタイを双方向エッジへ展開する（(src, tgt) で重複排除）。

    SocialEdge は無向関係を ``agent_id -> target_id`` の一方向で1回だけ保存する
    （network_generator は (min, max) で正規化）。一方 OpinionDynamicsEngine は
    ``adj[src].append((tgt, w))`` と片方向隣接しか張らないため、ミラーしないと
    意見が index 順（高→低）にしか流れず伝播が大きく偏る。ここで逆向きを補い、
    既に逆向きが存在する場合は二重計上を避けるため1本に畳む。
    """
    seen: set[tuple[str, str]] = set()
    result: list[dict] = []
    for e in edges:
        a, b = e["agent_id"], e["target_id"]
        strength = e.get("strength", 1.0)
        for src, tgt in ((a, b), (b, a)):
            if src == tgt or (src, tgt) in seen:
                continue
            seen.add((src, tgt))
            result.append({"agent_id": src, "target_id": tgt, "strength": strength})
    return result


def _stance_distribution(stances: list[str]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for s in stances:
        counts[s] = counts.get(s, 0) + 1
    total = len(stances)
    if total == 0:
        return {}
    return {k: round(v / total, 4) for k, v in counts.items()}


def build_engine_agents(
    agents: list[dict],
    response_map: dict[str, dict],
) -> list[dict]:
    """全人口を OpinionDynamicsEngine 入力形式へ変換する。

    活性化済み: stance×confidence の意見 + Big Five 由来の頑固さ。
    未活性化: 中立 (0.5) スタート + 頑固さ減衰（感化されやすい大衆）。
    """
    engine_agents = []
    for agent in agents:
        agent_id = agent["id"]
        big_five = agent.get("big_five", {})
        stubbornness = stubbornness_from_big_five(
            big_five.get("C", 0.5), agreeableness=big_five.get("A", 0.5),
        )
        resp = response_map.get(agent_id)
        if resp is not None:
            opinion = _convert_stance_to_opinion(
                resp.get("stance", "中立"), resp.get("confidence", 0.5),
            )
        else:
            opinion = [0.5]
            stubbornness = max(
                MIN_SUSCEPTIBLE_STUBBORNNESS,
                stubbornness * SUSCEPTIBILITY_DAMPENING,
            )
        engine_agents.append({
            "id": agent_id,
            "opinion_vector": opinion,
            "stubbornness": stubbornness,
        })
    return engine_agents


async def run_population_propagation(
    agents: list[dict],
    activation_responses: list[dict],
    edges: list[dict],
    *,
    seed: int | None = None,
    max_timesteps: int = 8,
    confidence_threshold: float = 0.5,
    on_round: Callable[[PropagationRoundDelta], Any] | None = None,
) -> PopulationPropagationResult:
    """全人口へ意見を伝播させる。

    Args:
        agents: 全人口のエージェント dict（id, agent_index, big_five を参照）。
        activation_responses: 活性化済み回答（agent_id, stance, confidence）。
        edges: SocialEdge dict（agent_id, target_id, strength）。
        seed: 決定論用シード（将来のノイズ導入に備えてエンジンへ渡す）。
        max_timesteps: 最大伝播ラウンド数。
        confidence_threshold: bounded confidence の閾値。
        on_round: ラウンドごとに PropagationRoundDelta を受け取るコールバック
            （同期/非同期どちらも可）。
    """
    if not agents:
        return PopulationPropagationResult(
            final_stances=[],
            distribution={},
            total_rounds=0,
            converged=True,
            rounds=[],
        )

    response_map = {r["agent_id"]: r for r in activation_responses}
    engine_agents = build_engine_agents(agents, response_map)

    # ソーシャルタイは無向だが一方向で保存されているため、双方向化してから
    # エンジンへ渡す（さもなくば伝播が index 順に偏る）。
    undirected_edges = _mirror_edges(edges)

    if is_enabled("heterogeneous_thresholds"):
        heterogeneous_thresholds = np.asarray(
            compute_heterogeneous_thresholds(
                agents,
                base_epsilon=confidence_threshold,
                seed=seed,
            ),
            dtype=np.float64,
        )
        if any(
            agent.get("information_source") or agent.get("information_sources")
            for agent in agents
        ):
            bubble_thresholds = compute_filter_bubble_thresholds(
                agents,
                base_epsilon=confidence_threshold,
            )
            engine_threshold = (
                heterogeneous_thresholds + bubble_thresholds
            ) / 2.0
        else:
            engine_threshold = heterogeneous_thresholds
    else:
        engine_threshold = confidence_threshold

    engine = OpinionDynamicsEngine(
        agents=engine_agents,
        edges=undirected_edges,
        confidence_threshold=engine_threshold,
        seed=seed,
    )

    prev_stances = [
        _convert_opinion_to_stance(ea["opinion_vector"]) for ea in engine_agents
    ]

    rounds: list[PropagationRoundDelta] = []
    converged = False

    for t in range(max_timesteps):
        step = engine.propagation_step(timestep=t)

        current_stances = [
            _convert_opinion_to_stance(op) for op in step.updated_opinions
        ]
        changes = []
        for i, (prev, curr) in enumerate(zip(prev_stances, current_stances)):
            if prev != curr:
                changes.append({
                    "agent_index": agents[i].get("agent_index", i),
                    "agent_id": agents[i]["id"],
                    "stance": curr,
                    "opinion": round(float(step.updated_opinions[i][0]), 4),
                })
        prev_stances = current_stances

        delta = PropagationRoundDelta(
            round=t,
            changes=changes,
            changed_count=len(changes),
            distribution=_stance_distribution(current_stances),
            max_delta=step.max_delta,
        )
        rounds.append(delta)

        if on_round is not None:
            if inspect.iscoroutinefunction(on_round):
                await on_round(delta)
            else:
                on_round(delta)

        if engine.detect_convergence(
            window=_CONVERGENCE_WINDOW, epsilon=_CONVERGENCE_EPSILON,
        ):
            converged = True
            logger.info("Population propagation converged at round %d", t)
            break

    final_opinions = [list(row) for row in engine._opinions]
    final_stances = [
        {
            "agent_id": agents[i]["id"],
            "agent_index": agents[i].get("agent_index", i),
            "stance": prev_stances[i],
            "opinion": round(float(final_opinions[i][0]), 4),
        }
        for i in range(len(agents))
    ]

    return PopulationPropagationResult(
        final_stances=final_stances,
        distribution=_stance_distribution(prev_stances),
        total_rounds=len(rounds),
        converged=converged,
        rounds=rounds,
    )
