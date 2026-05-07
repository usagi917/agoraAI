"""時間軸オーケストレーター: t0..t5 の 6 horizon を順次走らせる骨格

Wondrous Prancing Crayon Phase 1.
既存 `society_orchestrator` を破壊せず、step_fn を inject 可能な純粋構造にする。
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TimeStep:
    key: str
    label: str
    delta_days: int
    t_index: int


DEFAULT_HORIZONS: tuple[TimeStep, ...] = (
    TimeStep("t0", "即時", 0, 0),
    TimeStep("t1", "1週間後", 7, 1),
    TimeStep("t2", "1ヶ月後", 30, 2),
    TimeStep("t3", "6ヶ月後", 180, 3),
    TimeStep("t4", "1年後", 365, 4),
    TimeStep("t5", "3年後", 1095, 5),
)


@dataclass
class TimeStepSnapshot:
    step: TimeStep
    state: dict[str, Any]
    distribution: dict[str, float] = field(default_factory=dict)
    market_prices: list[float] | None = None
    metadata: dict[str, Any] | None = None


StepFn = Callable[[TimeStep, dict[str, Any]], "TimeStepSnapshot | Awaitable[TimeStepSnapshot]"]


class TimeAxisOrchestrator:
    """t0..t5 の 6 horizon を順番に走らせる純粋オーケストレーター.

    `step_fn(step, state)` を呼び出し、戻り値の `TimeStepSnapshot.state` を
    次の step の state として引き継ぐ。1 step が失敗しても残りは継続する。
    """

    def __init__(
        self,
        horizons: list[TimeStep] | tuple[TimeStep, ...] | None = None,
        on_step_started: Callable[[TimeStep], None] | None = None,
        on_step_completed: Callable[[TimeStep, TimeStepSnapshot], None] | None = None,
    ) -> None:
        self.horizons: tuple[TimeStep, ...] = tuple(horizons) if horizons else DEFAULT_HORIZONS
        self.on_step_started = on_step_started
        self.on_step_completed = on_step_completed

    async def run(
        self,
        initial_state: dict[str, Any],
        step_fn: StepFn,
    ) -> list[TimeStepSnapshot]:
        snapshots: list[TimeStepSnapshot] = []
        state = dict(initial_state) if initial_state else {}

        for step in self.horizons:
            if self.on_step_started is not None:
                try:
                    self.on_step_started(step)
                except Exception:
                    logger.exception("on_step_started callback failed at %s", step.key)

            snapshot: TimeStepSnapshot
            try:
                result = step_fn(step, state)
                if inspect.isawaitable(result):
                    result = await result
                snapshot = result
                state = snapshot.state
            except Exception as exc:
                logger.exception("time step %s failed: %s", step.key, exc)
                snapshot = TimeStepSnapshot(
                    step=step,
                    state=state,
                    distribution={},
                    metadata={"error": str(exc), "error_type": type(exc).__name__},
                )

            snapshots.append(snapshot)

            if self.on_step_completed is not None:
                try:
                    self.on_step_completed(step, snapshot)
                except Exception:
                    logger.exception("on_step_completed callback failed at %s", step.key)

        return snapshots


def horizons_summary(horizons: tuple[TimeStep, ...] = DEFAULT_HORIZONS) -> list[dict[str, Any]]:
    """API レスポンス用の辞書化."""
    return [
        {
            "key": h.key,
            "label": h.label,
            "delta_days": h.delta_days,
            "t_index": h.t_index,
        }
        for h in horizons
    ]
