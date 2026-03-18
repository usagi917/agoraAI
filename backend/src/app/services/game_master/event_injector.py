"""EventInjector: 外部イベント注入（条件/定期/ランダム）"""

import logging
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.environment_rule import EnvironmentRule

logger = logging.getLogger(__name__)


class EventInjector:
    """環境ルールに基づいてイベントを注入する。"""

    async def check_triggers(
        self,
        session: AsyncSession,
        run_id: str,
        round_number: int,
        world_state: dict,
    ) -> list[dict]:
        """ルールをチェックし、トリガーされたイベントを返す。"""
        result = await session.execute(
            select(EnvironmentRule).where(
                EnvironmentRule.run_id == run_id,
                EnvironmentRule.active == True,
            )
        )
        rules = result.scalars().all()

        events = []
        for rule in rules:
            if self._should_trigger(rule, round_number, world_state):
                event = self._create_event(rule, round_number)
                events.append(event)

                # トリガー履歴を更新
                rule.last_triggered_round = round_number
                if rule.rule_type == "trigger":
                    rule.active = False  # ワンショットトリガー

        if events:
            logger.info(f"Injected {len(events)} events at round {round_number}")

        return events

    def _should_trigger(
        self,
        rule: EnvironmentRule,
        round_number: int,
        world_state: dict,
    ) -> bool:
        """ルールがトリガーされるべきかを判定する。"""
        if rule.rule_type == "periodic":
            # 定期ルール: condition をラウンド間隔として解釈
            try:
                interval = int(rule.condition)
                return round_number % interval == 0
            except (ValueError, TypeError):
                return False

        elif rule.rule_type == "trigger":
            # 条件ルール: 確率ベース
            return random.random() < rule.probability

        elif rule.rule_type == "constraint":
            # 制約ルール: 常にアクティブ（後方で一貫性チェックに使う）
            return False

        return False

    def _create_event(self, rule: EnvironmentRule, round_number: int) -> dict:
        """ルールからイベントを生成する。"""
        return {
            "title": f"外部イベント: {rule.action[:50]}",
            "description": rule.action,
            "event_type": "emergence",
            "severity": rule.probability,
            "involved_entities": [],
            "source": "event_injector",
            "round_number": round_number,
        }
