"""構造化討論プロトコル: 主張→反論→再反論の3ラウンド構造"""

import json
import logging
import uuid
from dataclasses import dataclass, field

from src.app.llm.client import llm_client
from src.app.services.communication.message_bus import AgentMessage, MessageBus
from src.app.services.communication.conversation import ConversationChannel
from src.app.services.cost_tracker import record_usage
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


@dataclass
class Argument:
    """論証ノード。"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    claim: str = ""
    evidence: str = ""
    argument_type: str = "claim"  # claim|counter|rebuttal|support
    attacks: list[str] = field(default_factory=list)  # attacked argument IDs
    supports: list[str] = field(default_factory=list)  # supported argument IDs
    strength: float = 0.5


@dataclass
class DebateResult:
    """討論結果。"""
    channel_id: str = ""
    topic: str = ""
    arguments: list[Argument] = field(default_factory=list)
    winner_agent_id: str | None = None
    winning_argument: str = ""
    judge_reasoning: str = ""
    consensus_reached: bool = False


class DebateProtocol:
    """構造化討論: 3ラウンド（主張→反論→再反論）+ Judge評価。

    channel_type == "negotiation" 時に自動発動。
    """

    def __init__(self, max_rounds: int = 3):
        self.max_rounds = max_rounds

    async def run_debate(
        self,
        session,
        run_id: str,
        channel: ConversationChannel,
        participants: list[dict],
        topic: str,
        message_bus: MessageBus,
        round_number: int,
    ) -> DebateResult:
        """構造化討論を実行する。"""
        arguments: list[Argument] = []
        debate_result = DebateResult(channel_id=channel.id, topic=topic)

        # Phase 1: 各参加者が主張を提示
        claims = await self._generate_claims(
            session, run_id, participants, topic, round_number,
        )
        for claim in claims:
            arguments.append(claim)
            msg = AgentMessage(
                sender_id=claim.agent_id,
                recipient_ids=[p["id"] for p in participants if p["id"] != claim.agent_id],
                channel_id=channel.id,
                message_type="argue",
                content=f"[主張] {claim.claim}\n[根拠] {claim.evidence}",
                metadata={"argument_id": claim.id, "argument_type": "claim"},
                round_number=round_number,
            )
            message_bus.send(msg)

        # Phase 2: 反論
        if len(claims) >= 2:
            counters = await self._generate_counters(
                session, run_id, participants, claims, topic, round_number,
            )
            for counter in counters:
                arguments.append(counter)
                msg = AgentMessage(
                    sender_id=counter.agent_id,
                    recipient_ids=[p["id"] for p in participants if p["id"] != counter.agent_id],
                    channel_id=channel.id,
                    message_type="counter_argue",
                    content=f"[反論] {counter.claim}\n[根拠] {counter.evidence}",
                    metadata={"argument_id": counter.id, "argument_type": "counter"},
                    round_number=round_number,
                )
                message_bus.send(msg)

            # Phase 3: 再反論
            rebuttals = await self._generate_rebuttals(
                session, run_id, participants, claims, counters, topic, round_number,
            )
            for rebuttal in rebuttals:
                arguments.append(rebuttal)

        # Judge 評価
        debate_result.arguments = arguments
        judge_result = await self._judge_debate(
            session, run_id, arguments, topic, round_number,
        )
        debate_result.winner_agent_id = judge_result.get("winner_agent_id")
        debate_result.winning_argument = judge_result.get("winning_argument", "")
        debate_result.judge_reasoning = judge_result.get("reasoning", "")
        debate_result.consensus_reached = judge_result.get("consensus", False)

        # SSE: 討論結果をフロントエンドに配信
        try:
            await sse_manager.publish_debate_result(run_id, {
                "channel_id": channel.id,
                "topic": topic,
                "winner_agent_id": debate_result.winner_agent_id,
                "winning_argument": debate_result.winning_argument,
                "judge_reasoning": debate_result.judge_reasoning,
                "consensus_reached": debate_result.consensus_reached,
                "arguments": [
                    {"agent_id": a.agent_id, "claim": a.claim, "type": a.argument_type, "strength": a.strength}
                    for a in debate_result.arguments
                ],
            })
        except Exception:
            logger.warning("SSE publish failed for debate_result (topic=%s)", topic[:30])

        return debate_result

    async def _generate_claims(
        self, session, run_id, participants, topic, round_number,
    ) -> list[Argument]:
        """各参加者の初期主張をバッチ生成する。"""
        agents_desc = "\n".join(
            f"- {p.get('name', p['id'])} ({p.get('role', '')}): 目標={p.get('goals', [])}"
            for p in participants
        )

        system_prompt = """あなたは討論の主張生成システムです。
各参加者の立場から、議題に対する主張と根拠を生成してください。"""

        user_prompt = f"""議題: {topic}

## 参加者
{agents_desc}

## 出力形式（JSON）
{{
  "claims": [
    {{
      "agent_id": "エージェントID",
      "claim": "主張",
      "evidence": "根拠・証拠",
      "strength": 0.0-1.0
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

        result, usage = await llm_client.call_with_retry(
            task_name="negotiation",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )
        await record_usage(session, run_id, "debate_claims", usage)

        arguments = []
        if isinstance(result, dict):
            for c in result.get("claims", []):
                arguments.append(Argument(
                    agent_id=c.get("agent_id", ""),
                    claim=c.get("claim", ""),
                    evidence=c.get("evidence", ""),
                    argument_type="claim",
                    strength=c.get("strength", 0.5),
                ))
        return arguments

    async def _generate_counters(
        self, session, run_id, participants, claims, topic, round_number,
    ) -> list[Argument]:
        """反論を生成する。"""
        claims_text = "\n".join(
            f"- {c.agent_id}: {c.claim} (根拠: {c.evidence})"
            for c in claims
        )

        system_prompt = """あなたは討論の反論生成システムです。
既出の主張に対する反論を生成してください。"""

        user_prompt = f"""議題: {topic}

## 既出の主張
{claims_text}

## 参加者
{json.dumps([{"id": p["id"], "name": p.get("name", ""), "role": p.get("role", "")} for p in participants], ensure_ascii=False)}

## 出力形式（JSON）
{{
  "counters": [
    {{
      "agent_id": "反論するエージェントID",
      "target_agent_id": "反論対象のエージェントID",
      "claim": "反論内容",
      "evidence": "反論の根拠",
      "strength": 0.0-1.0
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

        result, usage = await llm_client.call_with_retry(
            task_name="negotiation",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )
        await record_usage(session, run_id, "debate_counters", usage)

        arguments = []
        if isinstance(result, dict):
            for c in result.get("counters", []):
                target_claim = next(
                    (cl for cl in claims if cl.agent_id == c.get("target_agent_id")),
                    None,
                )
                arg = Argument(
                    agent_id=c.get("agent_id", ""),
                    claim=c.get("claim", ""),
                    evidence=c.get("evidence", ""),
                    argument_type="counter",
                    attacks=[target_claim.id] if target_claim else [],
                    strength=c.get("strength", 0.5),
                )
                arguments.append(arg)
        return arguments

    async def _generate_rebuttals(
        self, session, run_id, participants, claims, counters, topic, round_number,
    ) -> list[Argument]:
        """再反論を生成する。"""
        context = "主張:\n" + "\n".join(f"  {c.agent_id}: {c.claim}" for c in claims)
        context += "\n反論:\n" + "\n".join(f"  {c.agent_id}: {c.claim}" for c in counters)

        system_prompt = """あなたは討論の再反論生成システムです。"""

        user_prompt = f"""議題: {topic}

## これまでの議論
{context}

## 出力形式（JSON）
{{
  "rebuttals": [
    {{
      "agent_id": "再反論するエージェントID",
      "claim": "再反論内容",
      "evidence": "根拠",
      "strength": 0.0-1.0
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

        result, usage = await llm_client.call_with_retry(
            task_name="negotiation",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )
        await record_usage(session, run_id, "debate_rebuttals", usage)

        arguments = []
        if isinstance(result, dict):
            for r in result.get("rebuttals", []):
                arguments.append(Argument(
                    agent_id=r.get("agent_id", ""),
                    claim=r.get("claim", ""),
                    evidence=r.get("evidence", ""),
                    argument_type="rebuttal",
                    strength=r.get("strength", 0.5),
                ))
        return arguments

    async def _judge_debate(
        self, session, run_id, arguments, topic, round_number,
    ) -> dict:
        """Judge agentが討論を評価する。"""
        args_text = "\n".join(
            f"- [{a.argument_type}] {a.agent_id}: {a.claim} (強度: {a.strength:.1f})"
            for a in arguments
        )

        system_prompt = """あなたは討論の審判です。
論証の質、根拠の強さ、論理的整合性を基準に評価してください。"""

        user_prompt = f"""議題: {topic}

## 論証一覧
{args_text}

## 出力形式（JSON）
{{
  "winner_agent_id": "最も説得力のあるエージェントID（合意の場合はnull）",
  "winning_argument": "勝利論証の要約",
  "reasoning": "評価の理由",
  "consensus": true/false,
  "argument_scores": [
    {{
      "agent_id": "ID",
      "score": 0.0-1.0,
      "feedback": "フィードバック"
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

        result, usage = await llm_client.call_with_retry(
            task_name="debate_judge",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )
        await record_usage(session, run_id, "debate_judge", usage)

        if isinstance(result, dict):
            return result
        return {"reasoning": "Judge evaluation failed", "consensus": False}
