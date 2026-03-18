"""AgentMemory: 3層統合インターフェース"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.llm.client import llm_client
from src.app.llm.prompts import MEMORY_IMPORTANCE_SYSTEM, MEMORY_IMPORTANCE_USER
from src.app.services.cost_tracker import record_usage
from src.app.services.memory.episodic import EpisodicMemory
from src.app.services.memory.semantic import SemanticMemory
from src.app.services.memory.procedural import ProceduralMemory
from src.app.services.memory.retrieval import MemoryRetriever
from src.app.services.memory.reflection import ReflectionEngine

logger = logging.getLogger(__name__)


class AgentMemory:
    """3層記憶の統合インターフェース。

    - episodic: 具体的な経験・出来事
    - semantic: 抽象化された知識・洞察（Reflectionの出力先）
    - procedural: 学習された行動パターン
    """

    def __init__(
        self,
        run_id: str,
        agent_id: str,
        agent_name: str,
        agent_role: str,
    ):
        self.run_id = run_id
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_role = agent_role

        # 設定読み込み
        config = settings.load_cognitive_config().get("memory", {})
        max_entries = config.get("episodic_max_entries", 100)

        # 3層記憶
        self.episodic = EpisodicMemory(run_id, agent_id, max_entries)
        self.semantic = SemanticMemory(run_id, agent_id)
        self.procedural = ProceduralMemory(run_id, agent_id)

        # 検索・Reflection
        self.retriever = MemoryRetriever(
            recency_weight=config.get("recency_weight", 1.0),
            relevance_weight=config.get("relevance_weight", 1.0),
            importance_weight=config.get("importance_weight", 1.0),
            recency_decay_lambda=config.get("recency_decay_lambda", 0.5),
        )
        self.reflection_engine = ReflectionEngine(
            threshold=config.get("reflection_threshold", 5),
            max_level=config.get("reflection_max_level", 2),
        )

        # Reflectionトリガー用カウンター
        self._new_episode_count = 0
        self._max_importance_since_reflection = 0.0

    async def record_experience(
        self,
        session: AsyncSession,
        content: str,
        round_number: int,
        embedding: list[float] | None = None,
    ) -> dict:
        """経験を記録する。重要度はLLMで判定する。"""
        importance = await self._assess_importance(session, content)

        entry = self.episodic.add(content, importance, round_number, embedding)
        self._new_episode_count += 1
        self._max_importance_since_reflection = max(
            self._max_importance_since_reflection, importance
        )

        return entry

    def retrieve_relevant(
        self,
        query_embedding: list[float] | None,
        current_round: int,
        top_k: int = 10,
    ) -> list[dict]:
        """全記憶層から関連記憶を検索する。"""
        all_entries = (
            self.episodic.get_all()
            + self.semantic.get_all()
            + self.procedural.get_all()
        )
        return self.retriever.retrieve(all_entries, query_embedding, current_round, top_k)

    async def maybe_reflect(
        self,
        session: AsyncSession,
        current_round: int,
    ) -> list[dict]:
        """必要に応じてReflectionを実行する。"""
        reflections = []

        # レベル1 Reflection
        if self.reflection_engine.should_reflect(
            self._new_episode_count, self._max_importance_since_reflection
        ):
            recent = self.episodic.get_recent(self.reflection_engine.threshold)
            level1 = await self.reflection_engine.reflect(
                session, self.run_id, self.agent_name, self.agent_role,
                recent, level=1,
            )

            for r in level1:
                self.semantic.add(
                    content=r["insight"],
                    importance=r.get("importance", 0.7),
                    round_number=current_round,
                    is_reflection=True,
                    reflection_level=1,
                    source_memory_ids=r.get("source_ids"),
                )
                reflections.append(r)

            self._new_episode_count = 0
            self._max_importance_since_reflection = 0.0

        # レベル2 Reflection
        level1_reflections = self.semantic.get_reflections(level=1)
        if self.reflection_engine.should_reflect_level2(len(level1_reflections)):
            level2 = await self.reflection_engine.reflect(
                session, self.run_id, self.agent_name, self.agent_role,
                level1_reflections, level=2,
            )
            for r in level2:
                self.semantic.add(
                    content=r["insight"],
                    importance=r.get("importance", 0.8),
                    round_number=current_round,
                    is_reflection=True,
                    reflection_level=2,
                    source_memory_ids=r.get("source_ids"),
                )
                reflections.append(r)

        return reflections

    async def _assess_importance(self, session: AsyncSession, content: str) -> float:
        """LLMで経験の重要度を判定する。"""
        user_prompt = MEMORY_IMPORTANCE_USER.format(
            agent_name=self.agent_name,
            agent_role=self.agent_role,
            experience=content,
        )

        result, usage = await llm_client.call(
            task_name="memory_importance",
            system_prompt=MEMORY_IMPORTANCE_SYSTEM,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        await record_usage(session, self.run_id, "memory_importance", usage)

        if isinstance(result, dict):
            return float(result.get("importance", 0.5))
        return 0.5

