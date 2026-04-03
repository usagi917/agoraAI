"""SSE イベントバス: in-memory pub/sub per run_id"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class SSEEvent:
    def __init__(self, event_type: str, run_id: str, payload: dict, sequence_no: int = 0):
        self.event_type = event_type
        self.run_id = run_id
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.sequence_no = sequence_no
        self.payload = payload

    def to_sse(self) -> str:
        data = {
            "event_type": self.event_type,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "sequence_no": self.sequence_no,
            "payload": self.payload,
        }
        return f"event: {self.event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_SUBSCRIBE_TIMEOUT = 60 * 30  # 30 minutes max per subscription


class SSEManager:
    def __init__(self):
        self._channels: dict[str, list[asyncio.Queue]] = {}
        self._sequences: dict[str, int] = {}
        self._aliases: dict[str, str] = {}  # source_id → target_id へフォワード

    def add_alias(self, source_id: str, target_id: str) -> None:
        """source_id への publish を target_id にもフォワードする。"""
        self._aliases[source_id] = target_id

    def remove_alias(self, source_id: str) -> None:
        """エイリアスを削除する。"""
        self._aliases.pop(source_id, None)

    def _next_seq(self, run_id: str) -> int:
        self._sequences[run_id] = self._sequences.get(run_id, 0) + 1
        return self._sequences[run_id]

    async def publish(self, run_id: str, event_type: str, payload: dict) -> None:
        seq = self._next_seq(run_id)
        event = SSEEvent(event_type, run_id, payload, seq)
        logger.info(f"SSE publish: {event_type} for run {run_id} (seq={seq})")

        if run_id in self._channels:
            for queue in self._channels[run_id]:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(f"Queue full for run {run_id}")

        # エイリアス先にもフォワード
        alias_target = self._aliases.get(run_id)
        if alias_target and alias_target in self._channels:
            alias_seq = self._next_seq(alias_target)
            alias_event = SSEEvent(event_type, alias_target, payload, alias_seq)
            for queue in self._channels[alias_target]:
                try:
                    queue.put_nowait(alias_event)
                except asyncio.QueueFull:
                    logger.warning(f"Queue full for alias {alias_target}")

    async def subscribe(self, run_id: str) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=100)
        if run_id not in self._channels:
            self._channels[run_id] = []
        self._channels[run_id].append(queue)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_SUBSCRIBE_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.warning(f"SSE subscription timed out for run {run_id}")
                    break
                yield event.to_sse()
                if event.event_type in (
                    "run_completed", "run_failed",
                    "swarm_completed", "swarm_failed",
                    "pipeline_completed", "simulation_completed", "simulation_failed",
                    "society_completed", "meeting_completed",
                ):
                    break
        finally:
            if run_id in self._channels:
                try:
                    self._channels[run_id].remove(queue)
                except ValueError:
                    pass
                if not self._channels[run_id]:
                    del self._channels[run_id]
                    self._sequences.pop(run_id, None)


    async def publish_agent_message(self, run_id: str, message_data: dict) -> None:
        """エージェント間メッセージイベントを発行する。"""
        await self.publish(run_id, "agent_message", message_data)

    async def publish_conversation_event(self, run_id: str, event_subtype: str, data: dict) -> None:
        """会話関連イベントを発行する。"""
        await self.publish(run_id, f"conversation_{event_subtype}", data)

    async def publish_debate_result(self, run_id: str, data: dict) -> None:
        """討論結果イベントを発行する。"""
        await self.publish(run_id, "debate_result", data)


sse_manager = SSEManager()
