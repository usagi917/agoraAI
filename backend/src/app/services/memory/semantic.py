"""SemanticMemory: 抽象化された知識・事実"""

import logging
import uuid

logger = logging.getLogger(__name__)


class SemanticMemory:
    """意味記憶: 抽象化された知識、事実、一般化された情報を保持する。"""

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
        is_reflection: bool = False,
        reflection_level: int = 0,
        source_memory_ids: list[str] | None = None,
    ) -> dict:
        """新しい意味記憶（知識・洞察）を追加する。"""
        entry = {
            "id": str(uuid.uuid4()),
            "memory_type": "semantic",
            "content": content,
            "importance": importance,
            "round_number": round_number,
            "embedding": embedding,
            "access_count": 0,
            "last_accessed_round": round_number,
            "is_reflection": is_reflection,
            "reflection_level": reflection_level,
            "source_memory_ids": source_memory_ids,
        }
        self._entries.append(entry)
        return entry

    def get_all(self) -> list[dict]:
        return list(self._entries)

    def get_reflections(self, level: int | None = None) -> list[dict]:
        """Reflection記憶を取得する。"""
        entries = [e for e in self._entries if e["is_reflection"]]
        if level is not None:
            entries = [e for e in entries if e["reflection_level"] == level]
        return entries

    def count(self) -> int:
        return len(self._entries)
