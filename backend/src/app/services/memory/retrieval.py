"""MemoryRetriever: recency x relevance x importance スコアリング"""

import math
import logging

import numpy as np

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """記憶検索: recency, relevance, importance の3軸でスコアリングする。

    score = alpha * exp(-lambda * (current_round - entry_round))   # recency
          + beta  * cosine_similarity(query_emb, entry_emb)        # relevance
          + gamma * importance                                      # importance
    """

    def __init__(
        self,
        recency_weight: float = 1.0,
        relevance_weight: float = 1.0,
        importance_weight: float = 1.0,
        recency_decay_lambda: float = 0.5,
    ):
        self.alpha = recency_weight
        self.beta = relevance_weight
        self.gamma = importance_weight
        self.decay_lambda = recency_decay_lambda

    def retrieve(
        self,
        entries: list[dict],
        query_embedding: list[float] | None,
        current_round: int,
        top_k: int = 10,
    ) -> list[dict]:
        """記憶エントリを3軸スコアでランク付けし、上位k件を返す。"""
        if not entries:
            return []

        scored = []
        for entry in entries:
            score = self._compute_score(entry, query_embedding, current_round)
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        # アクセスカウントを更新
        results = []
        for score, entry in scored[:top_k]:
            entry["access_count"] = entry.get("access_count", 0) + 1
            entry["last_accessed_round"] = current_round
            entry["_retrieval_score"] = score
            results.append(entry)

        return results

    def _compute_score(
        self,
        entry: dict,
        query_embedding: list[float] | None,
        current_round: int,
    ) -> float:
        """3軸スコアを計算する。"""
        # Recency
        rounds_ago = current_round - entry.get("round_number", 0)
        recency = math.exp(-self.decay_lambda * rounds_ago)

        # Relevance (cosine similarity)
        relevance = 0.0
        if query_embedding and entry.get("embedding"):
            relevance = self._cosine_similarity(query_embedding, entry["embedding"])

        # Importance
        importance = entry.get("importance", 0.5)

        return self.alpha * recency + self.beta * relevance + self.gamma * importance

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """2つのベクトルのコサイン類似度を計算する。"""
        a_arr = np.array(a)
        b_arr = np.array(b)
        dot = np.dot(a_arr, b_arr)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))
