"""軽量認知サイクル: REACTIVEエージェントのバッチ処理"""

import json
import logging

from src.app.llm.client import llm_client
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


class LightweightCognitiveProcessor:
    """REACTIVEエージェントを10体単位でバッチ処理する。

    40 REACTIVE agents → 4 LLM calls (vs 200 calls for full cycle)
    """

    def __init__(self, batch_size: int = 10):
        self.batch_size = batch_size

    async def process_batch(
        self,
        session,
        run_id: str,
        round_number: int,
        agents: list,
        world_state: dict,
        recent_events: list[dict],
        incoming_messages: dict[str, list] | None = None,
    ) -> list[dict]:
        """複数REACTIVEエージェントの行動を1回のLLM callで生成する。"""
        all_results = []
        incoming_messages = incoming_messages or {}

        for i in range(0, len(agents), self.batch_size):
            batch = agents[i:i + self.batch_size]
            results = await self._process_single_batch(
                session, run_id, round_number, batch, world_state,
                recent_events, incoming_messages,
            )
            all_results.extend(results)

        return all_results

    async def _process_single_batch(
        self,
        session,
        run_id: str,
        round_number: int,
        agents: list,
        world_state: dict,
        recent_events: list[dict],
        incoming_messages: dict[str, list],
    ) -> list[dict]:
        """1バッチ（最大10体）のエージェント行動を生成する。"""
        agents_desc = []
        for agent in agents:
            agent_id = agent.agent_id if hasattr(agent, "agent_id") else agent.get("id", "")
            name = agent.name if hasattr(agent, "name") else agent.get("name", "")
            role = agent.role if hasattr(agent, "role") else agent.get("role", "")
            goals = agent.goals if hasattr(agent, "goals") else agent.get("goals", [])

            msgs = incoming_messages.get(agent_id, [])
            msgs_text = ""
            if msgs:
                msgs_text = "受信メッセージ: " + "; ".join(
                    f"{m.sender_id}: {m.content}" if hasattr(m, "sender_id")
                    else f"{m.get('sender_id', '?')}: {m.get('content', '')}"
                    for m in msgs[:3]
                )

            agents_desc.append(
                f"- ID: {agent_id}, 名前: {name}, 役割: {role}, "
                f"目標: {json.dumps(goals[:2], ensure_ascii=False)}"
                + (f", {msgs_text}" if msgs_text else "")
            )

        world_summary = world_state.get("world_summary", "")[:1000]
        events_text = "\n".join(
            f"- {e.get('title', '')}: {e.get('description', '')}"
            for e in recent_events[:5]
        ) or "なし"

        system_prompt = """あなたは複数エージェントの行動を同時に生成するシステムです。
各エージェントの役割・目標・状況に基づいて、それぞれ短い行動を決定してください。
必ず JSON 形式で出力してください。"""

        user_prompt = f"""ラウンド {round_number}: 以下のエージェントの行動を生成してください。

## 世界状況
{world_summary}

## 最近のイベント
{events_text}

## エージェント一覧
{chr(10).join(agents_desc)}

## 出力形式（JSON）
{{
  "agent_actions": [
    {{
      "agent_id": "エージェントID",
      "action": "行動の簡潔な説明",
      "impact": "影響",
      "communication_intents": [
        {{
          "type": "say|propose|inform",
          "target_ids": ["対象ID"],
          "content": "メッセージ内容"
        }}
      ]
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

        result, usage = await llm_client.call_with_retry(
            task_name="batch_reactive_process",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        await record_usage(session, run_id, "batch_reactive_process", usage)

        if not isinstance(result, dict):
            logger.warning("Lightweight batch returned non-dict")
            return []

        actions = result.get("agent_actions", [])

        # エージェント結果を標準形式に変換
        results = []
        for action in actions:
            agent_id = action.get("agent_id", "")
            # agent_name を検索
            agent_name = ""
            for a in agents:
                aid = a.agent_id if hasattr(a, "agent_id") else a.get("id", "")
                if aid == agent_id:
                    agent_name = a.name if hasattr(a, "name") else a.get("name", "")
                    break

            results.append({
                "agent_id": agent_id,
                "agent_name": agent_name,
                "action": action.get("action", ""),
                "reasoning": "lightweight_cycle",
                "impact": action.get("impact", ""),
                "entity_updates": [],
                "relation_updates": [],
                "communication_intents": action.get("communication_intents", []),
            })

        return results
