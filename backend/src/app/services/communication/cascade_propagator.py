"""多段階会話伝播 (cascade propagator) — N ラウンド bandwagon + 確信度減衰."""

from __future__ import annotations

from collections import Counter

# スタンス -> 数値スコア (賛成方向 +1, 反対方向 -1, 中立 0)
_STANCE_SCORE: dict[str, float] = {
    "賛成": 1.0,
    "条件付き賛成": 0.5,
    "中立": 0.0,
    "条件付き反対": -0.5,
    "反対": -1.0,
}

# 数値スコアからスタンス（しきい値ベース）
_SCORE_THRESHOLDS: list[tuple[float, str]] = [
    (0.75, "賛成"),
    (0.25, "条件付き賛成"),
    (-0.25, "中立"),
    (-0.75, "条件付き反対"),
]


def _score_to_stance(score: float) -> str:
    for threshold, label in _SCORE_THRESHOLDS:
        if score >= threshold:
            return label
    return "反対"


def _build_neighbors(
    num_agents: int,
    edges: list[tuple[int, int]],
) -> dict[int, list[int]]:
    """無向グラフとして近傍辞書を構築する。"""
    neighbors: dict[int, list[int]] = {i: [] for i in range(num_agents)}
    for a, b in edges:
        if a == b:
            continue
        neighbors.setdefault(a, []).append(b)
        neighbors.setdefault(b, []).append(a)
    return neighbors


def _stance_distribution(snapshot: list[dict]) -> dict[str, float]:
    """スタンス占有率分布を返す。"""
    if not snapshot:
        return {}
    counts = Counter(r["stance"] for r in snapshot)
    total = len(snapshot)
    return {k: v / total for k, v in counts.items()}


class CascadePropagator:
    """N ラウンドの会話カスケード伝播器 (純粋関数, I/O や LLM 呼び出し無し)."""

    def __init__(self, num_rounds: int = 5, decay_factor: float = 0.85) -> None:
        self.num_rounds = num_rounds
        self.decay_factor = decay_factor

    def propagate(
        self,
        initial_responses: list[dict],
        graph_edges: list[tuple[int, int]],
        rounds: int | None = None,
    ) -> list[list[dict]]:
        """N ラウンド伝播を実行し、各ラウンドのスナップショットを返す。

        Returns: [初期スナップショット, ラウンド1後, ..., ラウンドN後]
        """
        n_rounds = rounds if rounds is not None else self.num_rounds

        # エージェント ID リストと現在状態を作る
        responses = [dict(r) for r in initial_responses]
        agent_ids = [r["agent_id"] for r in responses]
        # agent_id -> index
        index_of: dict[int, int] = {aid: i for i, aid in enumerate(agent_ids)}

        # 近傍 (index ベース)
        idx_edges: list[tuple[int, int]] = []
        for a, b in graph_edges:
            if a in index_of and b in index_of:
                idx_edges.append((index_of[a], index_of[b]))
        neighbors = _build_neighbors(len(responses), idx_edges)

        history: list[list[dict]] = [self._snapshot(responses)]

        for _round in range(n_rounds):
            new_responses = self._step(responses, neighbors)
            responses = new_responses
            history.append(self._snapshot(responses))

        return history

    def _step(
        self,
        responses: list[dict],
        neighbors: dict[int, list[int]],
    ) -> list[dict]:
        """1 ラウンド分の更新を計算する。"""
        new_responses: list[dict] = []
        for i, r in enumerate(responses):
            own_score = _STANCE_SCORE.get(r["stance"], 0.0)
            own_conf = float(r["confidence"])

            neigh_idx = neighbors.get(i, [])
            if neigh_idx:
                # 近傍多数派スコア (確信度で重み付け)
                neighbor_score = 0.0
                weight_sum = 0.0
                neighbor_stances: list[str] = []
                for j in neigh_idx:
                    nr = responses[j]
                    w = float(nr["confidence"])
                    neighbor_score += _STANCE_SCORE.get(nr["stance"], 0.0) * w
                    weight_sum += w
                    neighbor_stances.append(nr["stance"])
                if weight_sum > 0:
                    neighbor_score /= weight_sum
                else:
                    neighbor_score = 0.0

                # bandwagon pull: 多数派の占有率で引っ張りの強さを決定
                stance_counts = Counter(neighbor_stances)
                top_stance, top_count = stance_counts.most_common(1)[0]
                majority_share = top_count / len(neighbor_stances)
                # bandwagon 重み: 多数派が強いほど自分の意見より周りに寄る
                pull = majority_share * (1.0 - own_conf)
                blended = (1.0 - pull) * own_score + pull * neighbor_score
                new_stance = _score_to_stance(blended)
            else:
                new_stance = r["stance"]

            new_conf = own_conf * self.decay_factor
            # clamp to [0, 1]
            if new_conf < 0.0:
                new_conf = 0.0
            elif new_conf > 1.0:
                new_conf = 1.0

            new_responses.append({
                "agent_id": r["agent_id"],
                "stance": new_stance,
                "confidence": new_conf,
            })
        return new_responses

    @staticmethod
    def _snapshot(responses: list[dict]) -> list[dict]:
        return [
            {
                "agent_id": r["agent_id"],
                "stance": r["stance"],
                "confidence": float(r["confidence"]),
            }
            for r in responses
        ]

    @staticmethod
    def converged(rounds_history: list[list[dict]]) -> bool:
        """直近 2 ラウンドのスタンス分布変化が 1% 未満なら収束とみなす。"""
        if len(rounds_history) < 2:
            return False
        prev = _stance_distribution(rounds_history[-2])
        curr = _stance_distribution(rounds_history[-1])
        keys = set(prev) | set(curr)
        total_change = sum(abs(curr.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        return total_change < 0.01
