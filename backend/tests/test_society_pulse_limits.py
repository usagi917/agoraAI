"""society_pulse のフェーズ上限値が cognitive config から導出されることを検証する。"""

from src.app.services.phases.society_pulse import _phase_limits


class TestPhaseLimits:
    def test_reads_from_cognitive_config(self):
        cfg = {"game_master": {"max_active_agents": 64, "max_concurrent_agents": 12}}
        limits = _phase_limits(cfg)
        assert limits["target_count"] == 64
        assert limits["max_concurrency"] == 12

    def test_defaults_when_config_missing(self):
        limits = _phase_limits({})
        assert limits["target_count"] == 100
        assert limits["max_concurrency"] == 30

    def test_defaults_when_values_invalid(self):
        cfg = {"game_master": {"max_active_agents": "abc", "max_concurrent_agents": None}}
        limits = _phase_limits(cfg)
        assert limits["target_count"] == 100
        assert limits["max_concurrency"] == 30

    def test_rejects_non_positive_and_bool(self):
        cfg = {"game_master": {"max_active_agents": 0, "max_concurrent_agents": True}}
        limits = _phase_limits(cfg)
        assert limits["target_count"] == 100
        assert limits["max_concurrency"] == 30
