"""Phase 1: TimeAxisOrchestrator のテスト

t0..t5 の 6 horizon 走行と state 引き継ぎを検証する。
"""

from __future__ import annotations

import asyncio

import pytest


class TestTimeStepHorizons:
    """標準 horizons の構成."""

    def test_default_horizons_are_six(self):
        from src.app.services.society.time_axis_orchestrator import DEFAULT_HORIZONS

        assert len(DEFAULT_HORIZONS) == 6
        keys = [h.key for h in DEFAULT_HORIZONS]
        assert keys == ["t0", "t1", "t2", "t3", "t4", "t5"]

    def test_default_delta_days_are_monotonic(self):
        from src.app.services.society.time_axis_orchestrator import DEFAULT_HORIZONS

        deltas = [h.delta_days for h in DEFAULT_HORIZONS]
        assert deltas == sorted(deltas)
        assert deltas[0] == 0
        assert deltas[-1] == 1095

    def test_t_index_is_sequential(self):
        from src.app.services.society.time_axis_orchestrator import DEFAULT_HORIZONS

        for i, step in enumerate(DEFAULT_HORIZONS):
            assert step.t_index == i


class TestTimeAxisOrchestrator:
    """TimeAxisOrchestrator の振舞い."""

    def test_runs_all_horizons_in_order(self):
        from src.app.services.society.time_axis_orchestrator import (
            DEFAULT_HORIZONS,
            TimeAxisOrchestrator,
            TimeStepSnapshot,
        )

        observed_keys: list[str] = []

        async def step_fn(step, state):
            observed_keys.append(step.key)
            return TimeStepSnapshot(
                step=step,
                state={"counter": state.get("counter", 0) + 1},
                distribution={"中立": 1.0},
            )

        orchestrator = TimeAxisOrchestrator()
        snapshots = asyncio.run(orchestrator.run(initial_state={"counter": 0}, step_fn=step_fn))

        assert observed_keys == [h.key for h in DEFAULT_HORIZONS]
        assert len(snapshots) == 6

    def test_state_is_carried_to_next_step(self):
        from src.app.services.society.time_axis_orchestrator import (
            TimeAxisOrchestrator,
            TimeStepSnapshot,
        )

        async def step_fn(step, state):
            new_state = {"counter": state.get("counter", 0) + 1}
            return TimeStepSnapshot(step=step, state=new_state, distribution={})

        orchestrator = TimeAxisOrchestrator()
        snapshots = asyncio.run(orchestrator.run(initial_state={"counter": 0}, step_fn=step_fn))

        # 6 step 経過後に counter は 6
        assert snapshots[-1].state["counter"] == 6
        # 各 step の counter は単調増加
        counters = [s.state["counter"] for s in snapshots]
        assert counters == [1, 2, 3, 4, 5, 6]

    def test_lifecycle_callbacks_fire(self):
        from src.app.services.society.time_axis_orchestrator import (
            TimeAxisOrchestrator,
            TimeStepSnapshot,
        )

        started: list[str] = []
        completed: list[str] = []

        async def step_fn(step, state):
            return TimeStepSnapshot(step=step, state=state, distribution={})

        orchestrator = TimeAxisOrchestrator(
            on_step_started=lambda step: started.append(step.key),
            on_step_completed=lambda step, snap: completed.append(step.key),
        )
        asyncio.run(orchestrator.run(initial_state={}, step_fn=step_fn))

        assert started == ["t0", "t1", "t2", "t3", "t4", "t5"]
        assert completed == ["t0", "t1", "t2", "t3", "t4", "t5"]

    def test_step_failure_does_not_abort_pipeline(self):
        from src.app.services.society.time_axis_orchestrator import (
            TimeAxisOrchestrator,
            TimeStepSnapshot,
        )

        async def step_fn(step, state):
            if step.key == "t2":
                raise RuntimeError("simulated failure at t2")
            return TimeStepSnapshot(step=step, state=state, distribution={})

        orchestrator = TimeAxisOrchestrator()
        snapshots = asyncio.run(orchestrator.run(initial_state={}, step_fn=step_fn))

        # 6 step 全部の snapshot が返る
        assert len(snapshots) == 6
        # t2 のみ error
        t2 = next(s for s in snapshots if s.step.key == "t2")
        assert t2.metadata is not None and "error" in t2.metadata


class TestCustomHorizons:
    """カスタム horizons の指定."""

    def test_orchestrator_accepts_custom_horizons(self):
        from src.app.services.society.time_axis_orchestrator import (
            TimeAxisOrchestrator,
            TimeStep,
            TimeStepSnapshot,
        )

        custom = [
            TimeStep("now", "現在", 0, 0),
            TimeStep("year", "1年後", 365, 1),
        ]

        async def step_fn(step, state):
            return TimeStepSnapshot(step=step, state=state, distribution={})

        orchestrator = TimeAxisOrchestrator(horizons=custom)
        snapshots = asyncio.run(orchestrator.run(initial_state={}, step_fn=step_fn))

        assert len(snapshots) == 2
        assert snapshots[0].step.key == "now"
        assert snapshots[1].step.delta_days == 365
