"""society_pulse のフェーズ上限値が cognitive config から導出されることを検証する。"""

from src.app.services.phases.society_pulse import _phase_limits, _propagation_config


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


class TestPropagationConfig:
    def test_defaults_when_config_missing(self):
        cfg = _propagation_config({})
        assert cfg["enabled"] is True
        assert cfg["max_timesteps"] == 8
        assert cfg["confidence_threshold"] == 0.5

    def test_reads_from_cognitive_config(self):
        cfg = _propagation_config({
            "opinion_propagation": {
                "enabled": False,
                "max_timesteps": 12,
                "confidence_threshold": 0.3,
            }
        })
        assert cfg["enabled"] is False
        assert cfg["max_timesteps"] == 12
        assert cfg["confidence_threshold"] == 0.3

    def test_defaults_when_values_invalid(self):
        cfg = _propagation_config({
            "opinion_propagation": {
                "enabled": "yes",
                "max_timesteps": -3,
                "confidence_threshold": "wide",
            }
        })
        assert cfg["enabled"] is True
        assert cfg["max_timesteps"] == 8
        assert cfg["confidence_threshold"] == 0.5
