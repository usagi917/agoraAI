"""会話チャンネル管理: 直接対話、グループ、交渉"""

import logging
import uuid
from dataclasses import dataclass, field

from src.app.services.communication.message_bus import AgentMessage, MessageBus
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


@dataclass
class ConversationChannel:
    """会話チャンネル。"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel_type: str = "direct"  # direct|group|broadcast|negotiation
    participants: set[str] = field(default_factory=set)
    topic: str = ""
    max_turns: int = 8
    current_turn: int = 0
    state: str = "active"  # active|concluded|stalled
    initiator_id: str = ""


class ConversationManager:
    """会話の開始・進行・終了を管理する。"""

    def __init__(self, max_conversation_turns: int = 8):
        self._channels: dict[str, ConversationChannel] = {}
        self.max_conversation_turns = max_conversation_turns

    async def initiate_conversation(
        self,
        run_id: str,
        initiator_id: str,
        participant_ids: list[str],
        topic: str,
        channel_type: str = "direct",
    ) -> ConversationChannel:
        """新しい会話を開始する。"""
        channel = ConversationChannel(
            channel_type=channel_type,
            participants={initiator_id, *participant_ids},
            topic=topic,
            max_turns=self.max_conversation_turns,
            initiator_id=initiator_id,
        )
        self._channels[channel.id] = channel
        logger.info(
            "Conversation started: %s (type=%s, topic=%s, participants=%d)",
            channel.id[:8], channel_type, topic[:30], len(channel.participants),
        )

        await sse_manager.publish_conversation_event(run_id, "started", {
            "channel_id": channel.id,
            "channel_type": channel_type,
            "topic": topic,
            "participant_count": len(channel.participants),
            "participants": [str(p) for p in channel.participants],
            "initiator_id": initiator_id,
        })

        return channel

    def get_channel(self, channel_id: str) -> ConversationChannel | None:
        return self._channels.get(channel_id)

    def get_active_channels(self) -> list[ConversationChannel]:
        return [c for c in self._channels.values() if c.state == "active"]

    def get_agent_channels(self, agent_id: str) -> list[ConversationChannel]:
        return [
            c for c in self._channels.values()
            if agent_id in c.participants and c.state == "active"
        ]

    async def advance_turn(self, run_id: str, channel_id: str) -> bool:
        """会話ターンを進める。max_turnsに達したらFalseを返す。"""
        channel = self._channels.get(channel_id)
        if not channel or channel.state != "active":
            return False
        channel.current_turn += 1

        await sse_manager.publish_conversation_event(run_id, "turn_advanced", {
            "channel_id": channel_id,
            "current_turn": channel.current_turn,
            "max_turns": channel.max_turns,
        })

        if channel.current_turn >= channel.max_turns:
            channel.state = "concluded"
            logger.info("Conversation %s concluded (max turns)", channel_id[:8])
            await sse_manager.publish_conversation_event(run_id, "concluded", {
                "channel_id": channel_id,
                "reason": "max_turns",
            })
            return False
        return True

    async def conclude_channel(self, run_id: str, channel_id: str) -> None:
        channel = self._channels.get(channel_id)
        if channel:
            channel.state = "concluded"
            await sse_manager.publish_conversation_event(run_id, "concluded", {
                "channel_id": channel_id,
                "reason": "explicit",
            })

    async def process_conversation_round(
        self,
        run_id: str,
        channel: ConversationChannel,
        messages: list[AgentMessage],
        message_bus: MessageBus,
    ) -> list[AgentMessage]:
        """会話チャンネル内の1ターンのメッセージを処理する。"""
        for msg in messages:
            msg.channel_id = channel.id
            message_bus.send(msg)
        await self.advance_turn(run_id, channel.id)
        return messages

    @property
    def active_count(self) -> int:
        return len(self.get_active_channels())

    def flush_concluded(self) -> list[ConversationChannel]:
        """終了した会話チャンネルを返却してクリーンアップ。"""
        concluded = [c for c in self._channels.values() if c.state != "active"]
        for c in concluded:
            del self._channels[c.id]
        return concluded
