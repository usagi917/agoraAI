"""メッセージバス: エージェント間の非同期通信基盤"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """エージェント間メッセージ。"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    recipient_ids: list[str] = field(default_factory=list)  # empty=broadcast
    channel_id: Optional[str] = None
    message_type: str = "say"  # say|propose|accept|reject|inform|request|argue|counter_argue
    content: str = ""
    metadata: dict = field(default_factory=dict)  # intent, urgency, topics
    round_number: int = 0
    in_reply_to: Optional[str] = None


class MessageBus:
    """ラウンド内メッセージバッファリング + 配信。

    - send(): メッセージをバッファに追加
    - get_inbox(): エージェントの未読メッセージを取得
    - flush_round(): ラウンド終了時にバッファをクリア
    """

    def __init__(self):
        self._inbox: dict[str, list[AgentMessage]] = {}  # agent_id -> messages
        self._channels: dict[str, list[AgentMessage]] = {}  # channel_id -> messages
        self._message_log: list[AgentMessage] = []
        self._round_messages: list[AgentMessage] = []

    def send(self, message: AgentMessage) -> None:
        """メッセージを送信する。"""
        self._message_log.append(message)
        self._round_messages.append(message)

        if message.channel_id:
            if message.channel_id not in self._channels:
                self._channels[message.channel_id] = []
            self._channels[message.channel_id].append(message)

        # 配信先の決定
        if message.recipient_ids:
            # DM or group message
            for rid in message.recipient_ids:
                if rid not in self._inbox:
                    self._inbox[rid] = []
                self._inbox[rid].append(message)
        else:
            # broadcast: _inbox に追加はしない (RelevanceFilter で後から配信)
            pass

        logger.debug(
            "Message sent: %s -> %s (type=%s, channel=%s)",
            message.sender_id,
            message.recipient_ids or "broadcast",
            message.message_type,
            message.channel_id,
        )

    def get_inbox(self, agent_id: str) -> list[AgentMessage]:
        """エージェントの未読メッセージを取得しクリアする。"""
        messages = self._inbox.pop(agent_id, [])
        return messages

    def get_broadcasts(self) -> list[AgentMessage]:
        """ラウンド内のブロードキャストメッセージを取得する。"""
        return [m for m in self._round_messages if not m.recipient_ids]

    def get_channel_messages(self, channel_id: str) -> list[AgentMessage]:
        """チャンネルのメッセージ履歴を取得する。"""
        return self._channels.get(channel_id, [])

    def get_round_messages(self) -> list[AgentMessage]:
        """現在ラウンドの全メッセージを取得する。"""
        return list(self._round_messages)

    def flush_round(self) -> list[AgentMessage]:
        """ラウンド終了: バッファをクリアしてラウンドのメッセージを返す。"""
        messages = list(self._round_messages)
        self._round_messages.clear()
        self._inbox.clear()
        return messages

    @property
    def total_messages(self) -> int:
        return len(self._message_log)
