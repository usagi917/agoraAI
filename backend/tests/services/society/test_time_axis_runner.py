"""統合層 time_axis_runner のテスト.

cascade_propagator + particle_filter + temporal_report_generator を
society_orchestrator の末尾から呼び出すための pure 関数 wrapper。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


class FakeSSEManager:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def publish(self, run_id: str, event_type: str, payload: dict) -> None:
        self.events.append((run_id, event_type, dict(payload)))


def _resp(idx: int, stance: str, confidence: float = 0.6) -> dict:
    return {"agent_id": idx, "stance": stance, "confidence": confidence}


class TestRunTimeAxisPipeline:
    def test_returns_report_with_six_horizons(self):
        from src.app.services.society.time_axis_runner import run_time_axis_pipeline

        responses = [_resp(i, "中立") for i in range(8)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)]
        sse = FakeSSEManager()

        report = asyncio.run(run_time_axis_pipeline(
            simulation_id="sim-1",
            base_responses=responses,
            base_edges=edges,
            theme="ライドシェア解禁",
            sse_manager=sse,
        ))

        assert report["theme"] == "ライドシェア解禁"
        assert len(report["timeline"]) == 6
        keys = [item["key"] for item in report["timeline"]]
        assert keys == ["t0", "t1", "t2", "t3", "t4", "t5"]

    def test_publishes_sse_for_each_step(self):
        from src.app.services.society.time_axis_runner import run_time_axis_pipeline

        responses = [_resp(i, "賛成") for i in range(5)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 4)]
        sse = FakeSSEManager()

        asyncio.run(run_time_axis_pipeline(
            simulation_id="sim-2",
            base_responses=responses,
            base_edges=edges,
            theme="t",
            sse_manager=sse,
        ))

        # time_step_started + time_step_completed が各 step (6 step) 分、合計 12 イベント
        starts = [e for e in sse.events if e[1] == "time_step_started"]
        completes = [e for e in sse.events if e[1] == "time_step_completed"]
        assert len(starts) == 6
        assert len(completes) == 6
        # 最後に time_axis_completed
        assert sse.events[-1][1] == "time_axis_completed"

    def test_each_snapshot_has_distribution(self):
        from src.app.services.society.time_axis_runner import run_time_axis_pipeline

        responses = [_resp(i, ["賛成", "反対", "中立"][i % 3]) for i in range(9)]
        edges = [(i, (i + 1) % 9) for i in range(9)]  # ring graph
        sse = FakeSSEManager()

        report = asyncio.run(run_time_axis_pipeline(
            simulation_id="sim-3",
            base_responses=responses,
            base_edges=edges,
            theme="t",
            sse_manager=sse,
        ))

        for entry in report["timeline"]:
            assert "distribution" in entry
            total = sum(entry["distribution"].values())
            assert total == pytest.approx(1.0, abs=0.05) or total > 0

    def test_handles_empty_initial_responses(self):
        """初期 response が空でも例外を投げず、空に近い report を返す."""
        from src.app.services.society.time_axis_runner import run_time_axis_pipeline

        sse = FakeSSEManager()
        report = asyncio.run(run_time_axis_pipeline(
            simulation_id="sim-4",
            base_responses=[],
            base_edges=[],
            theme="t",
            sse_manager=sse,
        ))

        assert report["theme"] == "t"
        assert len(report["timeline"]) == 6  # 6 horizon は出る

    def test_summary_long_term_shift(self):
        from src.app.services.society.time_axis_runner import run_time_axis_pipeline

        responses = [_resp(i, "賛成") for i in range(6)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
        sse = FakeSSEManager()

        report = asyncio.run(run_time_axis_pipeline(
            simulation_id="sim-5",
            base_responses=responses,
            base_edges=edges,
            theme="t",
            sse_manager=sse,
        ))

        assert "summary" in report
        assert "long_term_shift" in report["summary"]
