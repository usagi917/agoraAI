"""CognitiveAgent: BDI状態 + 記憶 + ToMマップを保持する統合エージェント"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.models.agent_state import AgentState
from src.app.services.memory.agent_memory import AgentMemory
from src.app.services.cognition.bdi_engine import BDIReasoner, BeliefBase, Desire, Intention
from src.app.services.cognition.perception import PerceptionEngine
from src.app.services.cognition.deliberation import DeliberationEngine
from src.app.services.cognition.action_executor import ActionExecutor
from src.app.services.cognition.theory_of_mind import TheoryOfMindEngine

logger = logging.getLogger(__name__)


class CognitiveAgent:
    """認知エージェント: BDI + 3層記憶 + Theory of Mind。

    認知サイクル（1ラウンド）:
    1. perceive: 環境知覚
    2. update_beliefs: 信念更新
    3. deliberate: 熟慮・行動計画
    4. commit: 意図選択
    5. execute: 行動実行
    6. remember: 経験記録
    """

    def __init__(
        self,
        run_id: str,
        agent_profile: dict,
    ):
        self.run_id = run_id
        self.agent_id = agent_profile["id"]
        self.name = agent_profile["name"]
        self.role = agent_profile.get("role", "")
        self.entity_id = agent_profile.get("entity_id")
        self.goals = agent_profile.get("goals", [])
        self.relationships = agent_profile.get("relationships", [])

        # 設定読み込み
        cognitive_config = settings.load_cognitive_config().get("cognitive", {})
        bdi_config = cognitive_config.get("bdi", {})
        perception_config = cognitive_config.get("perception", {})

        # BDI状態の初期化
        reasoner = BDIReasoner(bdi_config.get("belief_update_threshold", 0.3))
        self.beliefs, self.desires, self.intentions = reasoner.initialize_from_agent_profile(agent_profile)
        self.bdi_reasoner = reasoner

        # コンポーネント
        self.perception = PerceptionEngine(
            visibility_radius=perception_config.get("visibility_radius", 0.7),
            noise_level=perception_config.get("noise_level", 0.1),
        )
        self.deliberation = DeliberationEngine(
            max_intentions=bdi_config.get("max_intentions", 3),
            commitment_decay=bdi_config.get("commitment_decay", 0.1),
        )
        self.executor = ActionExecutor()

        # 記憶
        self.memory = AgentMemory(run_id, self.agent_id, self.name, self.role)

        # Theory of Mind
        self.mental_models: dict[str, dict] = {}
        self.trust_map: dict[str, float] = {}

        # Theory of Mind エンジン
        tom_config = settings.load_cognitive_config().get("tom", {})
        self.tom_engine = TheoryOfMindEngine(
            max_models_per_agent=tom_config.get("max_models_per_agent", 5),
            update_frequency=tom_config.get("update_frequency", 2),
        ) if tom_config.get("enabled", False) else None

        # 通信状態
        self._incoming_messages: list[dict] = []
        self._communication_intents: list[dict] = []

        # 結果キャッシュ
        self._last_observations: list[dict] = []
        self._last_action: dict | None = None

    async def run_cognitive_cycle(
        self,
        session: AsyncSession,
        round_number: int,
        world_state: dict,
        recent_events: list[dict],
        message_bus=None,
    ) -> dict:
        """1ラウンド分の認知サイクルを実行する。"""
        # 0. メッセージ受信
        if message_bus:
            raw_messages = message_bus.get_inbox(self.agent_id)
            self._incoming_messages = [
                {"sender_id": m.sender_id, "message_type": m.message_type,
                 "content": m.content, "channel_id": m.channel_id,
                 "metadata": m.metadata}
                for m in raw_messages
            ]
        else:
            self._incoming_messages = []

        # 1. Perceive
        observations = await self.perceive(session, world_state, recent_events, round_number)

        # メッセージを観察に追加
        for msg in self._incoming_messages:
            observations.append({
                "content": f"[メッセージ] {msg.get('sender_id', '?')}から: {msg.get('content', '')}",
                "relevance": 0.7,
                "source": "message",
            })

        # 2. Update Beliefs
        self.update_beliefs(observations, round_number)

        # 3. Deliberate (メッセージコンテキスト付き)
        deliberation_result = await self.deliberate(session, round_number)

        # 4. Commit
        self.commit(deliberation_result, round_number)

        # ベイズ的信念更新
        for ev in deliberation_result.get("evidence_likelihoods", []):
            evidence = ev.get("evidence", "")
            lr = ev.get("likelihood_ratio", 1.0)
            if evidence and lr != 1.0:
                self.beliefs.bayesian_update(evidence, lr, round_number)

        # 5. Execute
        action_result = await self.execute(
            session, deliberation_result, world_state, round_number,
        )

        # 6. Communication intents → メッセージ送信
        self._communication_intents = deliberation_result.get("communication_intents", [])
        if message_bus:
            from src.app.services.communication.message_bus import AgentMessage
            for intent in self._communication_intents:
                msg = AgentMessage(
                    sender_id=self.agent_id,
                    recipient_ids=intent.get("target_ids", []),
                    message_type=intent.get("type", "say"),
                    content=intent.get("content", ""),
                    metadata={"urgency": intent.get("urgency", "normal")},
                    round_number=round_number,
                )
                message_bus.send(msg)

        # 7. Remember
        await self.remember(session, action_result, observations, round_number)

        # 8. Theory of Mind 更新
        if self.tom_engine and self.tom_engine.should_update(round_number):
            # 関係のあるエージェントのプロファイルを構築
            target_profiles = [
                {"id": rel.get("target_agent", ""), "name": rel.get("target_agent", ""), "role": ""}
                for rel in self.relationships[:self.tom_engine.max_models]
            ]
            if target_profiles:
                observed_actions = [
                    {"agent_id": e.get("involved_entities", [""])[0], "action": e.get("description", "")}
                    for e in recent_events if e.get("event_type") == "decision"
                ]
                self.mental_models = await self.tom_engine.infer_mental_models(
                    session, self.run_id, self.name, self.role,
                    target_profiles, observed_actions,
                    self._incoming_messages, self.mental_models,
                )
                self.trust_map = self.tom_engine.update_trust_map(
                    self.trust_map, self.mental_models,
                )

        # 状態をDB保存
        await self._save_state(session, round_number, deliberation_result, action_result)

        return {
            "agent_id": self.agent_id,
            "agent_name": self.name,
            "action": action_result.get("action_description", ""),
            "reasoning": deliberation_result.get("reasoning_chain", ""),
            "impact": action_result.get("impact", ""),
            "entity_updates": action_result.get("entity_updates", []),
            "relation_updates": action_result.get("relation_updates", []),
            "communication_intents": self._communication_intents,
        }

    async def perceive(
        self,
        session: AsyncSession,
        world_state: dict,
        recent_events: list[dict],
        round_number: int,
    ) -> list[dict]:
        """環境を知覚する。"""
        # 情報非対称性を適用
        filtered_env = self.perception.filter_environment(
            world_state, self.entity_id, self.relationships,
        )

        # 関連記憶を検索
        relevant_memories = self.memory.retrieve_relevant(
            query_embedding=None, current_round=round_number, top_k=5,
        )

        # LLMで観察を生成
        observations = await self.perception.perceive(
            session, self.run_id, self.name, self.role, self.goals,
            filtered_env, relevant_memories, recent_events,
        )

        self._last_observations = observations
        return observations

    def update_beliefs(self, observations: list[dict], round_number: int) -> None:
        """観察から信念を更新する。"""
        self.beliefs.update_from_observations(
            observations, round_number,
            threshold=self.bdi_reasoner.belief_update_threshold,
        )

    async def deliberate(self, session: AsyncSession, round_number: int) -> dict:
        """熟慮・行動計画を立てる。"""
        result = await self.deliberation.deliberate(
            session, self.run_id, self.name,
            beliefs=self.beliefs.to_list(),
            desires=[d.to_dict() for d in self.desires],
            intentions=[i.to_dict() for i in self.intentions],
            observations=self._last_observations,
            mental_models=self.mental_models,
            incoming_messages=self._incoming_messages,
        )
        return result

    def commit(self, deliberation_result: dict, round_number: int) -> None:
        """意図を確定する。"""
        # 既存意図のコミットメント減衰
        self.intentions = [
            Intention(i.plan_text, i.commitment_strength)
            for i in self.intentions
        ]
        decayed = self.deliberation.decay_commitments(
            [i.to_dict() for i in self.intentions]
        )
        self.intentions = [Intention(d["plan_text"], d["commitment_strength"]) for d in decayed]

        # 新しい意図を追加
        chosen = deliberation_result.get("chosen_action", "")
        strength = deliberation_result.get("commitment_strength", 0.7)
        if chosen:
            self.intentions.append(Intention(chosen, strength))

        # 信念更新
        belief_updates = deliberation_result.get("belief_updates", [])
        self.beliefs.update_from_deliberation(belief_updates, round_number)

    async def execute(
        self,
        session: AsyncSession,
        deliberation_result: dict,
        world_state: dict,
        round_number: int,
    ) -> dict:
        """行動を実行する。"""
        chosen_action = deliberation_result.get("chosen_action", "待機")
        context = {
            "round_number": round_number,
            "events": [],
            "world_summary": world_state.get("world_summary", ""),
        }

        result = await self.executor.execute(
            session, self.run_id, self.name, self.role, chosen_action, context,
        )

        self._last_action = result
        return result

    async def remember(
        self,
        session: AsyncSession,
        action_result: dict,
        observations: list[dict],
        round_number: int,
    ) -> None:
        """経験を記憶に記録し、必要に応じてReflectionを実行する。"""
        # 行動をエピソード記憶に記録
        action_desc = action_result.get("action_description", "")
        if action_desc:
            await self.memory.record_experience(
                session, f"[行動] {action_desc}", round_number,
            )

        # 重要な観察をエピソード記憶に記録
        for obs in observations:
            if obs.get("relevance", 0) >= 0.5:
                await self.memory.record_experience(
                    session, f"[観察] {obs['content']}", round_number,
                )

        # Reflectionチェック
        reflections = await self.memory.maybe_reflect(session, round_number)
        if reflections:
            logger.info(f"Agent {self.name} generated {len(reflections)} reflections")

    async def _save_state(
        self,
        session: AsyncSession,
        round_number: int,
        deliberation_result: dict,
        action_result: dict,
    ) -> None:
        """エージェント状態をDBに保存する。"""
        state = AgentState(
            id=str(uuid.uuid4()),
            run_id=self.run_id,
            agent_id=self.agent_id,
            round_number=round_number,
            beliefs=self.beliefs.to_list(),
            desires=[d.to_dict() for d in self.desires],
            intentions=[i.to_dict() for i in self.intentions],
            trust_map=self.trust_map,
            mental_models=self.mental_models,
            action_taken=action_result.get("action_description", ""),
            reasoning_chain=deliberation_result.get("reasoning_chain", ""),
        )
        session.add(state)

    @property
    def importance(self) -> float:
        """エージェントの重要度（アクティブエージェント選択用）。"""
        # 欲求の優先度平均 + 意図のコミットメント平均
        desire_avg = sum(d.priority for d in self.desires) / max(len(self.desires), 1)
        intention_avg = sum(i.commitment_strength for i in self.intentions) / max(len(self.intentions), 1)
        return (desire_avg + intention_avg) / 2
