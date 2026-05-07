"""P5-2: コスト/レイテンシ監視のテスト"""

import pytest


class TestCostMonitor:
    """コスト予算と監視のテスト."""

    def test_budget_tracking(self):
        """トークン使用量の追跡."""
        from src.app.services.society.cost_monitor import CostMonitor

        monitor = CostMonitor(budget_tokens=1000)
        monitor.record_usage(prompt_tokens=100, completion_tokens=50)
        monitor.record_usage(prompt_tokens=200, completion_tokens=100)

        assert monitor.total_tokens == 450
        assert monitor.remaining_budget == 550

    def test_budget_exceeded(self):
        """予算超過の検出."""
        from src.app.services.society.cost_monitor import CostMonitor

        monitor = CostMonitor(budget_tokens=100)
        monitor.record_usage(prompt_tokens=80, completion_tokens=30)

        assert monitor.is_budget_exceeded() is True

    def test_budget_not_exceeded(self):
        """予算内."""
        from src.app.services.society.cost_monitor import CostMonitor

        monitor = CostMonitor(budget_tokens=1000)
        monitor.record_usage(prompt_tokens=100, completion_tokens=50)

        assert monitor.is_budget_exceeded() is False

    def test_phase_timing(self):
        """フェーズ別タイミング計測."""
        from src.app.services.society.cost_monitor import CostMonitor

        monitor = CostMonitor(budget_tokens=10000)
        monitor.start_phase("population")
        monitor.end_phase("population")

        assert "population" in monitor.phase_timings
        assert monitor.phase_timings["population"] >= 0.0

    def test_summary(self):
        """サマリー取得."""
        from src.app.services.society.cost_monitor import CostMonitor

        monitor = CostMonitor(budget_tokens=5000)
        monitor.record_usage(prompt_tokens=100, completion_tokens=50)

        summary = monitor.get_summary()
        assert "total_tokens" in summary
        assert "remaining_budget" in summary
        assert "budget_exceeded" in summary
