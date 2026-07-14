"""Single-LLM stance-distribution ensemble tests."""

from unittest.mock import patch

import pytest

from src.app.services.society.constants import STANCE_ORDER


def _dist(*values: float) -> dict[str, float]:
    return dict(zip(STANCE_ORDER, values, strict=True))


class TestBlendDistributions:
    def test_convex_blend_and_normalization(self):
        from src.app.services.society.ensemble import blend_distributions

        swarm = _dist(0.5, 0.2, 0.1, 0.1, 0.1)
        single = _dist(0.1, 0.1, 0.2, 0.2, 0.4)

        result = blend_distributions(swarm, single, beta=0.75)

        assert list(result) == STANCE_ORDER
        assert sum(result.values()) == pytest.approx(1.0)
        assert result == pytest.approx(_dist(0.2, 0.125, 0.175, 0.175, 0.325))

    def test_missing_keys_are_zero_before_normalization(self):
        from src.app.services.society.ensemble import blend_distributions

        result = blend_distributions({"賛成": 1.0}, {"反対": 1.0}, beta=0.25)

        assert result == pytest.approx(_dist(0.75, 0.0, 0.0, 0.0, 0.25))

    @pytest.mark.parametrize("beta", [-0.01, 1.01])
    def test_rejects_beta_outside_unit_interval(self, beta):
        from src.app.services.society.ensemble import blend_distributions

        with pytest.raises(ValueError, match="beta"):
            blend_distributions({}, {}, beta)


class TestUniformFallback:
    def test_detects_uniform_distribution_with_tolerance(self):
        from src.app.services.society.ensemble import is_uniform_fallback

        nearly_uniform = _dist(0.2 + 1e-7, 0.2, 0.2, 0.2, 0.2 - 1e-7)
        assert is_uniform_fallback(nearly_uniform)

    def test_rejects_nonuniform_or_missing_distribution(self):
        from src.app.services.society.ensemble import is_uniform_fallback

        assert not is_uniform_fallback(_dist(0.3, 0.2, 0.2, 0.2, 0.1))
        assert not is_uniform_fallback({"賛成": 0.2})


class TestSelectEnsembleBeta:
    def test_selects_beta_with_lowest_mean_jsd(self):
        from src.app.services.society.ensemble import select_ensemble_beta

        swarm = _dist(1.0, 0.0, 0.0, 0.0, 0.0)
        single = _dist(0.0, 0.0, 0.0, 0.0, 1.0)
        truth = _dist(0.25, 0.0, 0.0, 0.0, 0.75)

        assert select_ensemble_beta([(swarm, single, truth)], betas=[0.0, 0.5, 0.75, 1.0]) == 0.75

    def test_default_grid_includes_five_percent_steps(self):
        from src.app.services.society.ensemble import select_ensemble_beta

        swarm = _dist(1.0, 0.0, 0.0, 0.0, 0.0)
        single = _dist(0.0, 0.0, 0.0, 0.0, 1.0)
        truth = _dist(0.15, 0.0, 0.0, 0.0, 0.85)

        assert select_ensemble_beta([(swarm, single, truth)]) == pytest.approx(0.85)


class TestGetEnsembleBeta:
    def test_reads_population_mix_setting(self):
        from src.app.services.society.ensemble import get_ensemble_beta, settings

        with patch.object(
            type(settings),
            "load_population_mix_config",
            return_value={"ensemble": {"single_llm_beta": 0.7}},
        ):
            assert get_ensemble_beta() == 0.7

    @pytest.mark.parametrize("config", [{}, {"ensemble": {}}])
    def test_defaults_when_key_is_missing(self, config):
        from src.app.services.society.ensemble import get_ensemble_beta, settings

        with patch.object(
            type(settings),
            "load_population_mix_config",
            return_value=config,
        ):
            assert get_ensemble_beta() == 0.85

    def test_defaults_when_config_load_fails(self):
        from src.app.services.society.ensemble import get_ensemble_beta, settings

        with patch.object(
            type(settings),
            "load_population_mix_config",
            side_effect=OSError("unavailable"),
        ):
            assert get_ensemble_beta() == 0.85
