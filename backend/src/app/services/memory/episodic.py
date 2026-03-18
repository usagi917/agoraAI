"""EpisodicMemory: 全経験のストリーム記録"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.memory_entry import MemoryEntry

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """エピソード記憶: 具体的な経験・出来事を時系列で記録する。"""

    def __init__(self, run_id: str, agent_id: str, max_entries: int = 100):
        self.run_id = run_id
        self.agent_id = agent_id
        self.max_entries = max_entries
        self._entries: list[dict] = []

    def add(
        self,
        content: str,
        importance: float,
        round_number: int,
        embedding: list[float] | None = None,
    ) -> dict:
        """新しいエピソード記憶を追加する。"""
        entry = {
            "id": str(uuid.uuid4()),
            "memory_type": "episodic",
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

        # max_entries を超えた場合は最も古い低重要度エントリを削除
        if len(self._entries) > self.max_entries:
            self._entries.sort(key=lambda e: e["importance"])
            self._entries.pop(0)

        return entry

    def get_recent(self, n: int = 10) -> list[dict]:
        """最近のN件のエピソード記憶を取得する。"""
        return sorted(self._entries, key=lambda e: e["round_number"], reverse=True)[:n]

    def get_all(self) -> list[dict]:
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)

    async def save_to_db(self, session: AsyncSession) -> None:
        """全エピソード記憶をDBに保存する。"""
        for entry in self._entries:
            mem = MemoryEntry(
                id=entry["id"],
                run_id=self.run_id,
                agent_id=self.agent_id,
                memory_type="episodic",
                content=entry["content"],
                importance=entry["importance"],
                round_number=entry["round_number"],
                embedding=entry.get("embedding"),
                access_count=entry["access_count"],
                last_accessed_round=entry["last_accessed_round"],
                is_reflection=entry["is_reflection"],
                reflection_level=entry["reflection_level"],
                source_memory_ids=entry.get("source_memory_ids"),
            )
            session.add(mem)

    def load_entries(self, entries: list[dict]) -> None:
        """外部から記憶エントリをロードする。"""
        self._entries = entries
