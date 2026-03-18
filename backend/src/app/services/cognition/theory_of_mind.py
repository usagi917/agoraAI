"""Theory of Mind: 他エージェントの意図・信念・行動を推論"""

import json
import logging

from src.app.llm.client import llm_client
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


class TheoryOfMindEngine:
    """Theory of Mind: 他エージェントのメンタル状態を推論する。

    - 受信メッセージ + 観察行動からバッチ推論 (5エージェント/1 call)
    - 既存の mental_models, trust_map フィールドに接続
    """

    def __init__(self, max_models_per_agent: int = 5, update_frequency: int = 2):
        self.max_models = max_models_per_agent
        self.update_frequency = update_frequency

    def should_update(self, round_number: int) -> bool:
        return round_number % self.update_frequency == 0

    async def infer_mental_models(
        self,
        session,
        run_id: str,
        agent_name: str,
        agent_role: str,
        target_agents: list[dict],
        observed_actions: list[dict],
        received_messages: list[dict],
        current_mental_models: dict[str, dict],
    ) -> dict[str, dict]:
        """他エージェントのメンタルモデルをバッチ推論する。"""
        if not target_agents:
            return current_mental_models

        # 最大5体をバッチ処理
        targets = target_agents[:self.max_models]

        targets_desc = []
        for t in targets:
            tid = t.get("id", "")
            tname = t.get("name", "")
            trole = t.get("role", "")

            # 観察された行動を抽出
            actions = [a for a in observed_actions if a.get("agent_id") == tid]
            actions_text = "; ".join(a.get("action", "") for a in actions[:3]) or "行動未観察"

            # 受信メッセージを抽出
            msgs = [m for m in received_messages if m.get("sender_id") == tid]
            msgs_text = "; ".join(m.get("content", "") for m in msgs[:3]) or "メッセージなし"

            # 現在のモデル
            current = current_mental_models.get(tid, {})
            current_text = json.dumps(current, ensure_ascii=False) if current else "初回推論"

            targets_desc.append(
                f"- ID: {tid}, 名前: {tname}, 役割: {trole}\n"
                f"  観察行動: {actions_text}\n"
                f"  受信メッセージ: {msgs_text}\n"
                f"  現在のモデル: {current_text}"
            )

        system_prompt = """あなたはTheory of Mind推論エンジンです。
観察対象エージェントの信念・欲求・意図・感情状態を推論してください。
推論はベイズ的に行い、既存モデルを新しい証拠で更新してください。"""

        user_prompt = f"""エージェント「{agent_name}」（{agent_role}）の視点から、
以下の対象エージェントのメンタル状態を推論してください。

## 推論対象
{chr(10).join(targets_desc)}

## 出力形式（JSON）
{{
  "mental_models": [
    {{
      "agent_id": "対象エージェントID",
      "predicted_beliefs": ["推定される信念1", "推定される信念2"],
      "predicted_goals": ["推定される目標1"],
      "predicted_action": "次に取りそうな行動",
      "emotional_state": "推定される感情状態",
      "trust_level": 0.0-1.0,
      "cooperation_likelihood": 0.0-1.0,
      "reasoning": "推論の根拠"
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

        result, usage = await llm_client.call_with_retry(
            task_name="tom_infer",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        await record_usage(session, run_id, f"tom_infer_{agent_name}", usage)

        updated_models = dict(current_mental_models)
        if isinstance(result, dict):
            for model in result.get("mental_models", []):
                tid = model.get("agent_id", "")
                if tid:
                    updated_models[tid] = {
                        "predicted_beliefs": model.get("predicted_beliefs", []),
                        "predicted_goals": model.get("predicted_goals", []),
                        "predicted_action": model.get("predicted_action", ""),
                        "emotional_state": model.get("emotional_state", ""),
                        "trust_level": model.get("trust_level", 0.5),
                        "cooperation_likelihood": model.get("cooperation_likelihood", 0.5),
                    }

        return updated_models

    def update_trust_map(
        self, trust_map: dict[str, float], mental_models: dict[str, dict],
    ) -> dict[str, float]:
        """メンタルモデルからtrust_mapを更新する。"""
        updated = dict(trust_map)
        for agent_id, model in mental_models.items():
            trust = model.get("trust_level", 0.5)
            if agent_id in updated:
                # 指数移動平均で更新
                updated[agent_id] = 0.7 * updated[agent_id] + 0.3 * trust
            else:
                updated[agent_id] = trust
        return updated
