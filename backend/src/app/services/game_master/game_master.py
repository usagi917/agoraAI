"""GameMaster: ラウンド実行のメインループ（Concordia方式）"""

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.models.timeline_event import TimelineEvent
from src.app.models.world_state import WorldState
from src.app.services.cognition.cognitive_agent import CognitiveAgent
from src.app.services.game_master.action_resolver import ActionResolver
from src.app.services.game_master.event_injector import EventInjector
from src.app.services.game_master.consistency_checker import ConsistencyChecker
from src.app.services.communication.message_bus import MessageBus, AgentMessage
from src.app.services.communication.conversation import ConversationManager
from src.app.services.communication.response_orchestrator import ResponseOrchestrator
from src.app.services.communication.debate_protocol import DebateProtocol
from src.app.services.scheduling.agent_scheduler import AgentScheduler, AgentTier
from src.app.services.cognition.lightweight_cycle import LightweightCognitiveProcessor
from src.app.services.cognition.causal_reasoning import CausalReasoningEngine
from src.app.models.message import Message
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


class GameMaster:
    """Game Master: 各ラウンドのオーケストレーション。

    run_round() フロー:
    1. イベント注入チェック
    2. 各エージェントの認知サイクル実行（並列、Semaphore制限）
    3. 行動の衝突解決
    4. 世界状態の更新
    5. 記憶の更新 + Reflection チェック
    6. 一貫性検証（設定ラウンドごと）
    """

    def __init__(self):
        config = settings.load_cognitive_config().get("game_master", {})
        self.max_active_agents = config.get("max_active_agents", 15)
        self.max_concurrent_agents = config.get("max_concurrent_agents", 10)
        self.conflict_resolution = config.get("conflict_resolution", "priority")
        self.enable_event_injection = config.get("enable_event_injection", True)

        self.action_resolver = ActionResolver(self.conflict_resolution)
        self.event_injector = EventInjector()
        self.consistency_checker = ConsistencyChecker(
            config.get("consistency_check_frequency", 2)
        )

        # 通信レイヤー
        comm_config = settings.load_cognitive_config().get("communication", {})
        self.message_bus = MessageBus()
        self.conversation_manager = ConversationManager(
            max_conversation_turns=comm_config.get("max_conversation_turns", 8),
        )
        self.response_orchestrator = ResponseOrchestrator(
            relevance_threshold=comm_config.get("relevance_threshold", 0.3),
            batch_size=comm_config.get("batch_response_size", 5),
        )
        self.debate_protocol = DebateProtocol() if comm_config.get("enable_structured_debate", False) else None

        # スケジューラー
        sched_config = settings.load_cognitive_config().get("scheduling", {})
        self.scheduler = AgentScheduler(
            protagonist_count=sched_config.get("protagonist_count", 8),
            active_count=sched_config.get("active_count", 22),
            reactive_count=sched_config.get("reactive_count", 40),
            reclassify_frequency=sched_config.get("reclassify_frequency", 2),
        )

        # 軽量処理 + 因果推論
        self.lightweight_processor = LightweightCognitiveProcessor()
        self.causal_engine = CausalReasoningEngine()

    async def run_round(
        self,
        session: AsyncSession,
        run_id: str,
        round_number: int,
        world_state: dict,
        cognitive_agents: list[CognitiveAgent],
        recent_events: list[dict],
        sse_channel: str | None = None,
    ) -> dict:
        """1ラウンド分のGame Masterループを実行する（4フェーズ構造）。"""
        channel = sse_channel or run_id
        all_events = list(recent_events)

        # イベント注入チェック
        if self.enable_event_injection:
            injected = await self.event_injector.check_triggers(
                session, run_id, round_number, world_state,
            )
            all_events.extend(injected)

        # 因果グラフ構築
        self.causal_engine.build_graph(world_state)

        # === Phase 0: エージェントTier分類 ===
        unread_counts = {
            a.agent_id: len(self.message_bus.get_inbox(a.agent_id))
            for a in cognitive_agents
        }
        # inbox を覗くだけなので get_inbox で消費されないよう注意
        # → 実際は get_inbox は pop するので、分類時点では peek が必要
        # 簡略化: 前ラウンドの通信量で分類
        active_convos = {
            a.agent_id: len(self.conversation_manager.get_agent_channels(a.agent_id))
            for a in cognitive_agents
        }
        classification = self.scheduler.classify(
            cognitive_agents,
            unread_counts={},  # 最初のラウンドはまだinboxがない
            active_conversations=active_convos,
        )

        protagonist_agents = self.scheduler.get_agents_by_tier(
            cognitive_agents, classification, AgentTier.PROTAGONIST)
        active_agents = self.scheduler.get_agents_by_tier(
            cognitive_agents, classification, AgentTier.ACTIVE)
        reactive_agents = self.scheduler.get_agents_by_tier(
            cognitive_agents, classification, AgentTier.REACTIVE)

        await sse_manager.publish(channel, "tier_classification", {
            "round": round_number,
            "protagonist": len(protagonist_agents),
            "active": len(active_agents),
            "reactive": len(reactive_agents),
            "dormant": len(cognitive_agents) - len(protagonist_agents) - len(active_agents) - len(reactive_agents),
        })

        # === Phase 1: 会話フェーズ ===
        # アクティブな会話チャンネルの処理
        for conv_channel in self.conversation_manager.get_active_channels():
            channel_messages = self.message_bus.get_channel_messages(conv_channel.id)
            if channel_messages:
                await sse_manager.publish(channel, "conversation_active", {
                    "channel_id": conv_channel.id,
                    "topic": conv_channel.topic,
                    "turn": conv_channel.current_turn,
                })

        # ブロードキャストメッセージの応答処理
        broadcasts = self.message_bus.get_broadcasts()
        agent_profiles = [
            {"id": a.agent_id, "name": a.name, "role": a.role,
             "goals": a.goals, "entity_id": a.entity_id,
             "relationships": a.relationships}
            for a in cognitive_agents
        ]
        for broadcast_msg in broadcasts:
            responses = await self.response_orchestrator.process_broadcast(
                session, run_id, broadcast_msg, agent_profiles,
            )
            for resp in responses:
                self.message_bus.send(resp)
                await sse_manager.publish(channel, "agent_message", {
                    "sender_id": resp.sender_id,
                    "recipient_ids": resp.recipient_ids,
                    "content": resp.content[:200],
                    "message_type": resp.message_type,
                })

        # === Phase 2: PROTAGONIST + ACTIVE フル認知サイクル ===
        full_cycle_agents = protagonist_agents + active_agents
        sem = asyncio.Semaphore(self.max_concurrent_agents)
        agent_results = await asyncio.gather(
            *[self._run_agent_with_sem(sem, agent, session, round_number, world_state, all_events)
              for agent in full_cycle_agents],
            return_exceptions=True,
        )

        successful_results = []
        for i, result in enumerate(agent_results):
            if isinstance(result, Exception):
                logger.warning(f"Agent {full_cycle_agents[i].name} cycle failed: {result}")
                continue
            successful_results.append(result)

            # communication_intents からのメッセージをSSEに送信
            for intent in result.get("communication_intents", []):
                await sse_manager.publish(channel, "agent_message", {
                    "sender_id": result.get("agent_id"),
                    "content": intent.get("content", "")[:200],
                    "message_type": intent.get("type", "say"),
                    "target_ids": intent.get("target_ids", []),
                })

        await sse_manager.publish(channel, "cognitive_cycles_completed", {
            "round": round_number,
            "full_cycle_agents": len(full_cycle_agents),
            "successful": len(successful_results),
        })

        # === Phase 3: REACTIVE 軽量バッチ処理 ===
        incoming_messages_map = {}
        for agent in reactive_agents:
            msgs = self.message_bus.get_inbox(agent.agent_id)
            if msgs:
                incoming_messages_map[agent.agent_id] = msgs

        reactive_results = await self.lightweight_processor.process_batch(
            session, run_id, round_number, reactive_agents,
            world_state, all_events, incoming_messages_map,
        )
        successful_results.extend(reactive_results)

        # REACTIVEの通信intentもメッセージバスに送信
        for result in reactive_results:
            for intent in result.get("communication_intents", []):
                msg = AgentMessage(
                    sender_id=result.get("agent_id", ""),
                    recipient_ids=intent.get("target_ids", []),
                    message_type=intent.get("type", "say"),
                    content=intent.get("content", ""),
                    metadata={"urgency": intent.get("urgency", "normal")},
                    round_number=round_number,
                )
                self.message_bus.send(msg)

        # === Phase 4: 行動解決 + 世界状態更新 ===
        resolved = await self.action_resolver.resolve(
            session, run_id, successful_results, world_state,
        )

        world_state = self._apply_agent_results(
            world_state,
            resolved if isinstance(resolved, list) and resolved and isinstance(resolved[0], dict) and "entity_updates" in resolved[0] else successful_results,
        )

        # メッセージをDB保存
        for msg in self.message_bus.get_round_messages():
            db_msg = Message(
                run_id=run_id,
                channel_id=msg.channel_id,
                sender_id=msg.sender_id,
                recipient_ids=msg.recipient_ids,
                message_type=msg.message_type,
                content=msg.content,
                metadata_json=msg.metadata,
                round_number=round_number,
                in_reply_to=msg.in_reply_to,
            )
            session.add(db_msg)

        # ラウンドのメッセージバッファをフラッシュ
        round_messages = self.message_bus.flush_round()

        # イベント生成
        for result in successful_results:
            event_data = {
                "title": f"{result.get('agent_name', 'Unknown')}の行動",
                "description": result.get("action", ""),
                "event_type": "decision",
                "severity": 0.5,
                "involved_entities": [result.get("agent_id", "")],
            }
            all_events.append(event_data)

            event = TimelineEvent(
                id=str(uuid.uuid4()),
                run_id=run_id,
                round_number=round_number,
                event_type="decision",
                title=event_data["title"],
                description=event_data["description"],
                severity=0.5,
                involved_entities=event_data["involved_entities"],
            )
            session.add(event)
            await sse_manager.publish(channel, "timeline_event", {
                "round": round_number,
                "event_type": "decision",
                "title": event_data["title"],
                "description": event_data["description"],
                "severity": 0.5,
                "involved_entities": event_data["involved_entities"],
            })

        # 一貫性検証
        if self.consistency_checker.should_check(round_number):
            check_result = await self.consistency_checker.validate(
                session, run_id, world_state, successful_results,
            )
            if not check_result.get("is_consistent", True):
                corrections = check_result.get("corrections", [])
                if corrections:
                    world_state = self.consistency_checker.apply_corrections(
                        world_state, corrections,
                    )

        # 終了した会話チャンネルのクリーンアップ
        self.conversation_manager.flush_concluded()

        # world_state をDB保存
        ws = WorldState(
            id=str(uuid.uuid4()),
            run_id=run_id,
            round_number=round_number,
            state_data=world_state,
        )
        session.add(ws)
        await session.flush()

        round_summary = self._generate_round_summary(successful_results, all_events)

        await sse_manager.publish(channel, "round_completed", {
            "round": round_number,
            "total_agents": len(cognitive_agents),
            "actions": len(successful_results),
            "messages": len(round_messages),
        })

        return {
            "round_result": {
                "agent_decisions": [
                    {"agent_id": r.get("agent_id"), "action": r.get("action", ""),
                     "reasoning": r.get("reasoning", ""), "impact": r.get("impact", "")}
                    for r in successful_results
                ],
                "entity_updates": self._collect_entity_updates(successful_results),
                "relation_updates": self._collect_relation_updates(successful_results),
                "events": [
                    {"title": e.get("title", ""), "description": e.get("description", ""),
                     "event_type": e.get("event_type", ""), "severity": e.get("severity", 0.5),
                     "involved_entities": e.get("involved_entities", [])}
                    for e in all_events
                ],
                "round_summary": round_summary,
                "messages_count": len(round_messages),
            },
            "updated_world_state": world_state,
        }

    async def _run_agent_with_sem(
        self,
        sem: asyncio.Semaphore,
        agent: CognitiveAgent,
        session: AsyncSession,
        round_number: int,
        world_state: dict,
        recent_events: list[dict],
    ) -> dict:
        """セマフォ制限付きでエージェントの認知サイクルを実行する。"""
        async with sem:
            return await agent.run_cognitive_cycle(
                session, round_number, world_state, recent_events,
                message_bus=self.message_bus,
            )

    def _apply_agent_results(
        self, world_state: dict, results: list[dict]
    ) -> dict:
        """エージェントの行動結果を世界状態に反映する。"""
        entity_map = {e["id"]: e for e in world_state.get("entities", [])}
        relation_map = {
            (r.get("source"), r.get("target")): r
            for r in world_state.get("relations", [])
        }

        for result in results:
            for update in result.get("entity_updates", []):
                eid = update.get("entity_id", "")
                if eid in entity_map:
                    changes = update.get("changes", {})
                    entity_map[eid].update(changes)

            for update in result.get("relation_updates", []):
                key = (update.get("source", ""), update.get("target", ""))
                if key in relation_map:
                    relation_map[key].update(update.get("changes", {}))

        world_state["entities"] = list(entity_map.values())
        return world_state

    def _collect_entity_updates(self, results: list[dict]) -> list[dict]:
        updates = []
        for r in results:
            updates.extend(r.get("entity_updates", []))
        return updates

    def _collect_relation_updates(self, results: list[dict]) -> list[dict]:
        updates = []
        for r in results:
            updates.extend(r.get("relation_updates", []))
        return updates

    def _generate_round_summary(self, results: list[dict], events: list[dict]) -> str:
        actions = [f"{r.get('agent_name', '?')}: {r.get('action', '?')}" for r in results[:5]]
        return f"ラウンド完了。{len(results)}エージェントが行動。主な行動: " + "; ".join(actions)
