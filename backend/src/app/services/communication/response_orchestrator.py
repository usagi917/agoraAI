"""応答効率化: 3層戦略でLLM呼び出しを最小化"""

import logging
import random
from dataclasses import dataclass

from src.app.llm.client import llm_client
from src.app.services.communication.message_bus import AgentMessage
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)

# 定型応答テンプレート
TEMPLATE_RESPONSES = {
    "acknowledge": [
        "了解しました。",
        "承知いたしました。",
        "理解しました。",
    ],
    "agree": [
        "同意します。",
        "その通りだと思います。",
        "賛成です。",
    ],
    "disagree": [
        "その点については異論があります。",
        "別の見方もあると思います。",
    ],
    "defer": [
        "検討させていただきます。",
        "もう少し情報が必要です。",
    ],
}


@dataclass
class ResponseCandidate:
    agent_id: str
    agent_name: str
    agent_role: str
    relevance_score: float
    response_type: str = "llm"  # llm|template|skip


class RelevanceFilter:
    """層1: broadcastメッセージの応答候補をフィルタリング（LLM不要）。"""

    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold

    def filter_respondents(
        self,
        message: AgentMessage,
        agents: list[dict],
    ) -> list[ResponseCandidate]:
        """メッセージに応答すべきエージェントを選定する。"""
        candidates = []
        msg_topics = message.metadata.get("topics", [])
        msg_entities = message.metadata.get("entities", [])

        for agent in agents:
            if agent["id"] == message.sender_id:
                continue

            score = self._compute_relevance(agent, msg_topics, msg_entities, message)
            if score >= self.threshold:
                candidates.append(ResponseCandidate(
                    agent_id=agent["id"],
                    agent_name=agent.get("name", ""),
                    agent_role=agent.get("role", ""),
                    relevance_score=score,
                ))

        candidates.sort(key=lambda c: c.relevance_score, reverse=True)
        return candidates

    def _compute_relevance(
        self, agent: dict, topics: list[str], entities: list[str], message: AgentMessage,
    ) -> float:
        score = 0.0
        agent_goals = " ".join(agent.get("goals", []))
        agent_role = agent.get("role", "")

        # トピック一致
        for topic in topics:
            if topic.lower() in agent_goals.lower() or topic.lower() in agent_role.lower():
                score += 0.3

        # エンティティ関連
        agent_entity = agent.get("entity_id", "")
        for eid in entities:
            if eid == agent_entity:
                score += 0.4

        # 関係性チェック
        for rel in agent.get("relationships", []):
            if rel.get("target_agent") == message.sender_id:
                score += 0.3 * rel.get("strength", 0.5)

        # urgency bonus
        if message.metadata.get("urgency", "normal") == "high":
            score += 0.1

        return min(score, 1.0)


class TemplateResponder:
    """層3: 定型応答をパターンマッチで生成（LLM不要）。"""

    def can_respond(self, candidate: ResponseCandidate, message: AgentMessage) -> bool:
        """定型応答で処理可能かどうか。"""
        if message.message_type in ("inform",):
            return True
        if candidate.relevance_score < 0.4:
            return True
        return False

    def generate(self, message: AgentMessage, candidate: ResponseCandidate) -> AgentMessage:
        """定型応答を生成する。"""
        if message.message_type == "propose":
            template_key = "defer"
        elif message.message_type == "inform":
            template_key = "acknowledge"
        else:
            template_key = "acknowledge"

        content = random.choice(TEMPLATE_RESPONSES.get(template_key, TEMPLATE_RESPONSES["acknowledge"]))

        return AgentMessage(
            sender_id=candidate.agent_id,
            recipient_ids=[message.sender_id],
            channel_id=message.channel_id,
            message_type="say",
            content=content,
            metadata={"generated_by": "template", "template_key": template_key},
            round_number=message.round_number,
            in_reply_to=message.id,
        )


class BatchResponseGenerator:
    """層2: 同一会話の複数エージェント応答を1回のLLM callで生成。"""

    def __init__(self, batch_size: int = 5):
        self.batch_size = batch_size

    async def generate_batch(
        self,
        session,
        run_id: str,
        message: AgentMessage,
        candidates: list[ResponseCandidate],
        conversation_context: str = "",
    ) -> list[AgentMessage]:
        """複数エージェントの応答を1回のLLM呼び出しで生成する。"""
        if not candidates:
            return []

        agents_desc = "\n".join(
            f"- {c.agent_name} ({c.agent_role}): 関連度 {c.relevance_score:.1f}"
            for c in candidates
        )

        system_prompt = """あなたは複数エージェントの応答を同時に生成するシステムです。
各エージェントの役割と性格に基づいて、それぞれ異なる自然な応答を生成してください。
必ず JSON 形式で出力してください。"""

        user_prompt = f"""以下のメッセージに対する各エージェントの応答を生成してください。

## 受信メッセージ
送信者: {message.sender_id}
種別: {message.message_type}
内容: {message.content}

## 会話コンテキスト
{conversation_context or "なし"}

## 応答すべきエージェント
{agents_desc}

## 出力形式（JSON）
{{
  "responses": [
    {{
      "agent_id": "エージェントID",
      "content": "応答内容",
      "message_type": "say|propose|accept|reject|inform|request",
      "intent": "応答の意図"
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

        result, usage = await llm_client.call_with_retry(
            task_name="batch_conversation_respond",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        await record_usage(session, run_id, "batch_conversation_respond", usage)

        messages = []
        if isinstance(result, dict):
            for resp in result.get("responses", []):
                msg = AgentMessage(
                    sender_id=resp.get("agent_id", ""),
                    recipient_ids=[message.sender_id],
                    channel_id=message.channel_id,
                    message_type=resp.get("message_type", "say"),
                    content=resp.get("content", ""),
                    metadata={
                        "generated_by": "batch_llm",
                        "intent": resp.get("intent", ""),
                    },
                    round_number=message.round_number,
                    in_reply_to=message.id,
                )
                messages.append(msg)

        return messages


class ResponseOrchestrator:
    """3層応答効率化のオーケストレーター。

    層1: RelevanceFilter (LLM不要) - broadcast→候補絞り込み
    層2: BatchResponseGenerator (1 call/N体) - バッチLLM応答
    層3: TemplateResponder (LLM不要) - 定型応答
    """

    def __init__(
        self,
        relevance_threshold: float = 0.3,
        batch_size: int = 5,
    ):
        self.filter = RelevanceFilter(threshold=relevance_threshold)
        self.template = TemplateResponder()
        self.batch_gen = BatchResponseGenerator(batch_size=batch_size)
        self.batch_size = batch_size

    async def process_broadcast(
        self,
        session,
        run_id: str,
        message: AgentMessage,
        all_agents: list[dict],
        conversation_context: str = "",
    ) -> list[AgentMessage]:
        """broadcastメッセージに対する応答を効率的に生成する。"""
        # 層1: 関連性フィルタ
        candidates = self.filter.filter_respondents(message, all_agents)
        logger.info(
            "Broadcast filter: %d/%d agents selected for message from %s",
            len(candidates), len(all_agents), message.sender_id,
        )

        if not candidates:
            return []

        # 層3: 定型応答で処理可能な候補を分離
        template_candidates = []
        llm_candidates = []
        for c in candidates:
            if self.template.can_respond(c, message):
                c.response_type = "template"
                template_candidates.append(c)
            else:
                c.response_type = "llm"
                llm_candidates.append(c)

        responses = []

        # 定型応答の生成
        for c in template_candidates:
            responses.append(self.template.generate(message, c))

        # 層2: LLM バッチ応答
        for i in range(0, len(llm_candidates), self.batch_size):
            batch = llm_candidates[i:i + self.batch_size]
            batch_responses = await self.batch_gen.generate_batch(
                session, run_id, message, batch, conversation_context,
            )
            responses.extend(batch_responses)

        return responses
