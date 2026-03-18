"""ProceduralMemory: 学習された行動パターン"""

import logging
import uuid

logger = logging.getLogger(__name__)


class ProceduralMemory:
    """手続き記憶: 学習された行動パターン、成功/失敗した戦略を記録する。"""

    def __init__(self, run_id: str, agent_id: str):
        self.run_id = run_id
        self.agent_id = agent_id
        self._entries: list[dict] = []

    def add(
        self,
        content: str,
        importance: float,
        round_number: int,
        embedding: list[float] | None = None,
    ) -> dict:
        """新しい手続き記憶（行動パターン）を追加する。"""
        entry = {
            "id": str(uuid.uuid4()),
            "memory_type": "procedural",
            "content": content,
            "importance": importance,
            "round_number": round_number,
            "embedding": embedding,
            "access_count": 0,
            "last_accessed_round": round_number,
            "is_reflection": False,
            "reflection_level": 0,
            "source_memory_ids": None,
        }
        self._entries.append(entry)
        return entry

    def get_relevant_patterns(self, context: str) -> list[dict]:
        """コンテキストに関連する行動パターンを取得する。

        embeddingベースの検索はretrievalモジュールに委譲するため、
        ここでは全エントリを返す。
        """
        return list(self._entries)

    def get_all(self) -> list[dict]:
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)
