"""ReflectionEngine: エピソード群 → 高次洞察の合成（再帰2レベル）"""

import logging

from src.app.llm.client import llm_client
from src.app.llm.prompts import REFLECTION_SYSTEM, REFLECTION_USER
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """Reflection: エピソード記憶から高次洞察を合成する。

    - レベル1: エピソード → 洞察
    - レベル2: レベル1洞察群 → 更に高次の洞察
    """

    def __init__(
        self,
        threshold: int = 5,
        max_level: int = 2,
        level2_threshold: int = 10,
    ):
        self.threshold = threshold
        self.max_level = max_level
        self.level2_threshold = level2_threshold

    def should_reflect(self, new_episode_count: int, max_importance: float) -> bool:
        """Reflectionが必要かどうかを判定する。"""
        if new_episode_count >= self.threshold:
            return True
        if max_importance > 0.8:
            return True
        return False

    def should_reflect_level2(self, level1_count: int) -> bool:
        """レベル2 Reflectionが必要かどうかを判定する。"""
        return self.max_level >= 2 and level1_count >= self.level2_threshold

    async def reflect(
        self,
        session,
        run_id: str,
        agent_name: str,
        agent_role: str,
        episodes: list[dict],
        level: int = 1,
    ) -> list[dict]:
        """エピソード群から高次洞察を生成する。"""
        if not episodes:
            return []

        experiences_text = "\n".join(
            f"[{e.get('round_number', '?')}] (重要度: {e.get('importance', 0.5):.1f}) {e['content']}"
            for e in episodes
        )

        user_prompt = REFLECTION_USER.format(
            agent_name=agent_name,
            agent_role=agent_role,
            experiences=experiences_text,
        )

        result, usage = await llm_client.call_with_retry(
            task_name="reflection",
            system_prompt=REFLECTION_SYSTEM,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        await record_usage(session, run_id, f"reflection_level{level}", usage)

        if not isinstance(result, dict):
            logger.warning(f"Reflection returned non-dict for {agent_name}")
            return []

        reflections = result.get("reflections", [])
        for r in reflections:
            r["reflection_level"] = level
            r["is_reflection"] = True

        logger.info(f"Generated {len(reflections)} level-{level} reflections for {agent_name}")
        return reflections

    async def self_critique(
        self,
        session,
        run_id: str,
        agent_name: str,
        agent_role: str,
        recent_action: str,
        expected_outcome: str,
        actual_observations: list[dict],
    ) -> dict:
        """自己批判 (Shinn et al. 2023 Reflexion): 行動と結果を批判的に評価する。

        PROTAGONIST のみ適用。
        """
        observations_text = "\n".join(
            f"- {o.get('content', '')}" for o in actual_observations[:10]
        ) or "観察なし"

        system_prompt = """あなたはエージェントの自己批判システムです（Reflexionフレームワーク）。
エージェントの最近の行動を批判的に評価し、改善提案を生成してください。
成功と失敗の両方を公平に分析してください。"""

        user_prompt = f"""エージェント「{agent_name}」（{agent_role}）の行動を自己批判してください。

## 最近の行動
{recent_action}

## 期待した結果
{expected_outcome}

## 実際の観察
{observations_text}

## 出力形式（JSON）
{{
  "critique": "行動の批判的評価",
  "success_aspects": ["成功した点"],
  "failure_aspects": ["改善が必要な点"],
  "lessons_learned": ["学んだ教訓"],
  "revised_strategy": "修正された戦略提案",
  "confidence_adjustment": -0.2 to 0.2
}}

重要: 必ず有効な JSON のみを出力してください。"""

        result, usage = await llm_client.call_with_retry(
            task_name="self_critique",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        await record_usage(session, run_id, f"self_critique_{agent_name}", usage)

        if isinstance(result, dict):
            return result
        return {
            "critique": "自己批判の生成に失敗",
            "success_aspects": [],
            "failure_aspects": [],
            "lessons_learned": [],
            "revised_strategy": "",
            "confidence_adjustment": 0.0,
        }
