"""Phase 10: 時系列統合レポートのテスト"""

from __future__ import annotations

import pytest


def _snapshot(key: str, label: str, delta_days: int, t_index: int, distribution=None, market=None):
    from src.app.services.society.time_axis_orchestrator import TimeStep, TimeStepSnapshot

    return TimeStepSnapshot(
        step=TimeStep(key, label, delta_days, t_index),
        state={"counter": t_index},
        distribution=distribution or {"賛成": 0.4, "反対": 0.4, "中立": 0.2},
        market_prices=market,
    )


class TestTemporalReportGenerator:
    def test_report_contains_all_horizons(self):
        from src.app.services.society.temporal_report_generator import TemporalReportGenerator

        snaps = [_snapshot(f"t{i}", f"step {i}", i * 30, i) for i in range(6)]
        gen = TemporalReportGenerator()
        report = gen.generate(snapshots=snaps, theme="ライドシェア解禁")

        assert report["theme"] == "ライドシェア解禁"
        assert len(report["timeline"]) == 6
        keys = [item["key"] for item in report["timeline"]]
        assert keys == ["t0", "t1", "t2", "t3", "t4", "t5"]

    def test_report_includes_driving_factors_per_step(self):
        from src.app.services.society.temporal_report_generator import TemporalReportGenerator

        snaps = [
            _snapshot("t0", "now", 0, 0, distribution={"賛成": 0.5, "反対": 0.5}),
            _snapshot("t1", "1w", 7, 1, distribution={"賛成": 0.7, "反対": 0.3}),
        ]
        gen = TemporalReportGenerator()
        report = gen.generate(snapshots=snaps, theme="t")

        # t1 の駆動要因として賛成が +0.2 など出る
        t1 = report["timeline"][1]
        assert "driving_factors" in t1
        # 賛成 が増加方向としてリストに入る
        assert any(f["stance"] == "賛成" and f["delta"] > 0 for f in t1["driving_factors"])

    def test_report_includes_credible_intervals_when_provided(self):
        from src.app.services.society.temporal_report_generator import TemporalReportGenerator

        snaps = [_snapshot("t0", "now", 0, 0)]
        ci_per_step = {
            "t0": {"50": {"賛成": {"lower": 0.3, "median": 0.4, "upper": 0.5}}}
        }
        gen = TemporalReportGenerator()
        report = gen.generate(snapshots=snaps, theme="t", ci_per_step=ci_per_step)

        assert "credible_intervals" in report["timeline"][0]
        assert report["timeline"][0]["credible_intervals"]["50"]["賛成"]["median"] == 0.4

    def test_what_if_panel_is_built_when_alt_provided(self):
        from src.app.services.society.temporal_report_generator import TemporalReportGenerator

        baseline = [_snapshot("t0", "now", 0, 0, distribution={"賛成": 0.4, "反対": 0.4, "中立": 0.2})]
        alt = [_snapshot("t0", "now", 0, 0, distribution={"賛成": 0.6, "反対": 0.3, "中立": 0.1})]

        gen = TemporalReportGenerator()
        report = gen.generate(snapshots=baseline, alternative_snapshots=alt, theme="t")

        assert "what_if" in report
        # 賛成 が +0.2 されている
        what_if = report["what_if"]
        first = what_if[0]
        assert first["delta"]["賛成"] == pytest.approx(0.2, abs=1e-6)

    def test_summary_aggregates_movement(self):
        from src.app.services.society.temporal_report_generator import TemporalReportGenerator

        snaps = [
            _snapshot("t0", "now", 0, 0, distribution={"賛成": 0.4, "反対": 0.6}),
            _snapshot("t5", "3y", 1095, 5, distribution={"賛成": 0.7, "反対": 0.3}),
        ]
        gen = TemporalReportGenerator()
        report = gen.generate(snapshots=snaps, theme="t")

        assert "summary" in report
        # 賛成 が長期で +0.3
        assert report["summary"]["long_term_shift"]["賛成"] == pytest.approx(0.3, abs=1e-6)
