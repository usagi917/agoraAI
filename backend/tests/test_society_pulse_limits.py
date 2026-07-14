"""society_pulse のフェーズ上限値が cognitive config から導出されることを検証する。"""

from src.app.services.phases.society_pulse import (
    _activation_limits,
    _calibrate_social_distribution,
    _phase_limits,
    _propagation_config,
    _select_narrative_pairs,
    _updated_activation_phase_data,
    _visualized_agents,
)
from src.app.services.society.hybrid_config import load_hybrid_inference_config


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

    def test_allows_full_population_activation(self):
        cfg = {"game_master": {"max_active_agents": 10_000, "max_concurrent_agents": 2}}

        limits = _phase_limits(cfg)

        assert limits == {"target_count": 10_000, "max_concurrency": 2}

    def test_hybrid_limits_override_legacy_only_on_hybrid_execution_path(self):
        hybrid = load_hybrid_inference_config(
            {
                "enabled": True,
                "population_activation": {
                    "provider": "liquid",
                    "target_count": 10_000,
                    "max_concurrency": 1,
                },
            }
        )
        cognitive = {"game_master": {"max_active_agents": 100, "max_concurrent_agents": 30}}

        assert _activation_limits(hybrid, diagnostic=False, cognitive_config=cognitive) == {
            "target_count": 10_000,
            "max_concurrency": 1,
        }
        assert _activation_limits(hybrid, diagnostic=True, cognitive_config=cognitive) == {
            "target_count": 100,
            "max_concurrency": 30,
        }

    def test_disabled_hybrid_keeps_legacy_paid_path_bounded(self):
        hybrid = load_hybrid_inference_config({"enabled": False})
        cognitive = {"game_master": {"max_active_agents": 100, "max_concurrent_agents": 30}}

        assert _activation_limits(hybrid, diagnostic=False, cognitive_config=cognitive) == {
            "target_count": 100,
            "max_concurrency": 30,
        }


class TestPropagationConfig:
    def test_defaults_when_config_missing(self):
        cfg = _propagation_config({})
        assert cfg["enabled"] is True
        assert cfg["max_timesteps"] == 8
        assert cfg["confidence_threshold"] == 0.5


class TestLargePopulationPayloadLimits:
    def test_visualization_is_bounded_without_changing_activation_population(self):
        agents = [{"id": f"a-{index}"} for index in range(10_000)]

        visualized = _visualized_agents(agents, limit=200)

        assert len(agents) == 10_000
        assert len(visualized) == 200
        assert visualized[0]["id"] == "a-0"
        assert visualized[-1]["id"] == "a-199"

    def test_narrative_sample_round_robins_across_stances(self):
        agents = [{"id": f"a-{index}"} for index in range(8)]
        responses = [
            {"stance": "賛成", "confidence": 0.9},
            {"stance": "賛成", "confidence": 0.8},
            {"stance": "賛成", "confidence": 0.7},
            {"stance": "反対", "confidence": 0.95},
            {"stance": "反対", "confidence": 0.6},
            {"stance": "中立", "confidence": 0.85},
            {"stance": "条件付き賛成", "confidence": 0.75},
            {"stance": "", "confidence": 0.0, "_failed": True},
        ]

        pairs = _select_narrative_pairs(agents, responses, limit=4)

        assert len(pairs) == 4
        assert {response["stance"] for _, response in pairs} == {
            "賛成",
            "反対",
            "中立",
            "条件付き賛成",
        }
        assert all(not response.get("_failed") for _, response in pairs)

    def test_social_distribution_keeps_learned_gpt_residual_in_final_prediction(self):
        aggregation = {
            "hybrid_calibration": {
                "applied": True,
                "shrinkage": 0.5,
                "residual": {"賛成": -0.2, "反対": 0.2},
            }
        }

        corrected = _calibrate_social_distribution(
            {"賛成": 0.5, "反対": 0.5},
            aggregation,
        )

        assert aggregation["stance_distribution_social_liquid"] == {
            "賛成": 0.5,
            "反対": 0.5,
        }
        assert aggregation["stance_distribution_social_hybrid_full"] == {
            "賛成": 0.3,
            "反対": 0.7,
            "条件付き賛成": 0.0,
            "条件付き反対": 0.0,
            "中立": 0.0,
        }
        assert corrected["賛成"] == 0.4
        assert corrected["反対"] == 0.6

    def test_final_social_distribution_refreshes_durable_activation_audit(self):
        phase_data = {
            "aggregation": {"stance_distribution": {"賛成": 0.7, "反対": 0.3}},
            "responses_summary": {
                "total": 10_000,
                "stance_distribution": {"賛成": 0.7, "反対": 0.3},
            },
        }
        final_aggregation = {
            "stance_distribution_social_liquid": {"賛成": 0.5, "反対": 0.5},
            "stance_distribution": {"賛成": 0.4, "反対": 0.6},
        }

        updated = _updated_activation_phase_data(phase_data, final_aggregation)

        assert updated["aggregation"] == final_aggregation
        assert updated["responses_summary"]["total"] == 10_000
        assert updated["responses_summary"]["stance_distribution"] == {
            "賛成": 0.4,
            "反対": 0.6,
        }

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
