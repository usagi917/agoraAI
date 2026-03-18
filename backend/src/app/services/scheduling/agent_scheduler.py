"""4段階Tier分類: エージェントをPROTAGONIST/ACTIVE/REACTIVE/DORMANTに動的分類"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class AgentTier(Enum):
    PROTAGONIST = "protagonist"  # 常にフル認知 (8体)
    ACTIVE = "active"            # フル認知 (22体)
    REACTIVE = "reactive"        # 軽量サイクル (40体)
    DORMANT = "dormant"          # 休止、メッセージ受信のみ (30体)


class AgentScheduler:
    """エージェントを動的にTier分類する。

    スコア = 未読メッセージ数×0.3 + importance×0.3 + 直近行動インパクト×0.2 + アクティブ会話数×0.2

    Tier分類:
    - PROTAGONIST: スコア上位 protagonist_count 体
    - ACTIVE: 次の active_count 体
    - REACTIVE: 次の reactive_count 体
    - DORMANT: 残り
    """

    def __init__(
        self,
        protagonist_count: int = 8,
        active_count: int = 22,
        reactive_count: int = 40,
        reclassify_frequency: int = 2,
    ):
        self.protagonist_count = protagonist_count
        self.active_count = active_count
        self.reactive_count = reactive_count
        self.reclassify_frequency = reclassify_frequency
        self._last_classification: dict[str, AgentTier] = {}
        self._round_count = 0

    def classify(
        self,
        agents: list,
        unread_counts: dict[str, int] | None = None,
        active_conversations: dict[str, int] | None = None,
        action_impacts: dict[str, float] | None = None,
    ) -> dict[str, AgentTier]:
        """全エージェントをTier分類する。"""
        self._round_count += 1
        unread_counts = unread_counts or {}
        active_conversations = active_conversations or {}
        action_impacts = action_impacts or {}

        # 再分類頻度チェック (毎ラウンドではなく設定頻度で再分類)
        if (
            self._last_classification
            and self._round_count % self.reclassify_frequency != 0
        ):
            return self._last_classification

        # スコア計算
        scored = []
        for agent in agents:
            agent_id = agent.agent_id if hasattr(agent, "agent_id") else agent.get("id", "")
            importance = agent.importance if hasattr(agent, "importance") else agent.get("importance", 0.5)

            score = (
                unread_counts.get(agent_id, 0) * 0.3
                + importance * 0.3
                + action_impacts.get(agent_id, 0.0) * 0.2
                + active_conversations.get(agent_id, 0) * 0.2
            )
            scored.append((agent_id, score))

        # スコア降順ソート
        scored.sort(key=lambda x: x[1], reverse=True)

        # Tier割り当て
        classification = {}
        for i, (agent_id, score) in enumerate(scored):
            if i < self.protagonist_count:
                classification[agent_id] = AgentTier.PROTAGONIST
            elif i < self.protagonist_count + self.active_count:
                classification[agent_id] = AgentTier.ACTIVE
            elif i < self.protagonist_count + self.active_count + self.reactive_count:
                classification[agent_id] = AgentTier.REACTIVE
            else:
                classification[agent_id] = AgentTier.DORMANT

        self._last_classification = classification

        # ログ出力
        tier_counts = {}
        for tier in classification.values():
            tier_counts[tier.value] = tier_counts.get(tier.value, 0) + 1
        logger.info("Agent tier classification: %s", tier_counts)

        return classification

    def get_agents_by_tier(
        self, agents: list, classification: dict[str, AgentTier], tier: AgentTier,
    ) -> list:
        """指定Tierのエージェントリストを返す。"""
        result = []
        for agent in agents:
            agent_id = agent.agent_id if hasattr(agent, "agent_id") else agent.get("id", "")
            if classification.get(agent_id) == tier:
                result.append(agent)
        return result
