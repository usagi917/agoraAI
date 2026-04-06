"""人口生成サービスのテスト: 分布特性、スキーマ検証"""

import pytest

from src.app.config import settings
from src.app.services.society.population_generator import (
    generate_population,
    generate_agent_profile,
    get_population_size_bounds,
    validate_population_size,
    _generate_big_five,
)


class TestGenerateAgentProfile:
    def test_population_size_bounds_follow_config(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            type(settings),
            "load_population_mix_config",
            lambda self: {"population": {"default_size": 250, "min_size": 120, "max_size": 400}},
        )
        assert get_population_size_bounds() == (250, 120, 400)

    def test_validate_population_size_uses_configured_range(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            type(settings),
            "load_population_mix_config",
            lambda self: {"population": {"default_size": 250, "min_size": 120, "max_size": 400}},
        )
        with pytest.raises(ValueError, match="120〜400"):
            validate_population_size(401)

    def test_profile_has_required_fields(self):
        profile = generate_agent_profile(
            index=0,
            population_id="test-pop",
            pop_config={},
            mix_config={},
            total=100,
        )
        assert "id" in profile
        assert profile["population_id"] == "test-pop"
        assert profile["agent_index"] == 0
        assert "demographics" in profile
        assert "big_five" in profile
        assert "values" in profile
        assert "shock_sensitivity" in profile
        assert "llm_backend" in profile

    def test_demographics_structure(self):
        profile = generate_agent_profile(0, "pop", {}, {}, 100)
        demo = profile["demographics"]
        assert "age" in demo
        assert "gender" in demo
        assert "occupation" in demo
        assert "region" in demo
        assert "income_bracket" in demo
        assert "education" in demo
        assert 18 <= demo["age"] <= 85

    def test_big_five_range(self):
        profile = generate_agent_profile(0, "pop", {}, {}, 100)
        bf = profile["big_five"]
        for trait in ["O", "C", "E", "A", "N"]:
            assert trait in bf
            assert 0.0 <= bf[trait] <= 1.0

    def test_shock_sensitivity_topics(self):
        profile = generate_agent_profile(0, "pop", {}, {}, 100)
        shock = profile["shock_sensitivity"]
        assert len(shock) > 0
        for topic, value in shock.items():
            assert 0.0 <= value <= 1.0

    def test_census_age_distribution_respects_bounds(self):
        pop_config = {
            "demographics": {
                "age": {
                    "distribution": "census",
                    "min": 18,
                    "max": 85,
                }
            }
        }
        ages = [
            generate_agent_profile(i, "pop", pop_config, {}, 100)["demographics"]["age"]
            for i in range(200)
        ]
        assert all(18 <= age <= 85 for age in ages)


class TestGeneratePopulation:
    @pytest.mark.asyncio
    async def test_uses_config_default_count_when_omitted(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            type(settings),
            "load_population_mix_config",
            lambda self: {"population": {"default_size": 12, "min_size": 5, "max_size": 20}},
        )
        agents = await generate_population("test-pop", seed=42)
        assert len(agents) == 12

    @pytest.mark.asyncio
    async def test_generates_correct_count(self):
        agents = await generate_population("test-pop", count=50, seed=42)
        assert len(agents) == 50

    @pytest.mark.asyncio
    async def test_deterministic_with_seed(self):
        agents1 = await generate_population("pop1", count=20, seed=123)
        agents2 = await generate_population("pop2", count=20, seed=123)
        # Same seed should produce same demographics (modulo different population_ids)
        for a1, a2 in zip(agents1, agents2):
            assert a1["demographics"] == a2["demographics"]
            assert a1["big_five"] == a2["big_five"]

    @pytest.mark.asyncio
    async def test_age_distribution(self):
        agents = await generate_population("pop", count=500, seed=42)
        ages = [a["demographics"]["age"] for a in agents]
        avg_age = sum(ages) / len(ages)
        # Mean should be roughly 42 (default)
        assert 35 <= avg_age <= 50

    @pytest.mark.asyncio
    async def test_gender_distribution(self):
        agents = await generate_population("pop", count=1000, seed=42)
        genders = [a["demographics"]["gender"] for a in agents]
        male_ratio = genders.count("male") / len(genders)
        female_ratio = genders.count("female") / len(genders)
        # Should be roughly 49% each
        assert 0.40 <= male_ratio <= 0.58
        assert 0.40 <= female_ratio <= 0.58

    @pytest.mark.asyncio
    async def test_unique_ids(self):
        agents = await generate_population("pop", count=100, seed=42)
        ids = [a["id"] for a in agents]
        assert len(set(ids)) == 100

    @pytest.mark.asyncio
    async def test_llm_backend_assignment(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            type(settings),
            "load_population_mix_config",
            lambda self: {
                "activation_layer": {
                    "weights": {
                        "openai": 0.5,
                        "gemini": 0.5,
                    }
                }
            },
        )
        agents = await generate_population("pop", count=200, seed=42)
        backends = set(a["llm_backend"] for a in agents)
        assert backends <= {"openai", "gemini"}
        assert len(backends) >= 2


# ---------------------------------------------------------------------------
# Phase D: 多変量正規分布 Big Five テスト
# ---------------------------------------------------------------------------


class TestMultivariateBigFive:
    """Phase D: Big Five が多変量正規分布で生成され、相関・非対称性を持つことを検証。"""

    def _generate_many(self, n: int = 1000) -> list[dict]:
        """n 件の Big Five を生成するヘルパー。"""
        import random
        random.seed(42)
        return [_generate_big_five({}) for _ in range(n)]

    def test_traits_are_correlated(self):
        """O-E 間に正の相関があること (multivariate Normal の結果)。"""
        samples = self._generate_many(2000)
        o_vals = [s["O"] for s in samples]
        e_vals = [s["E"] for s in samples]

        # ピアソン相関を手計算
        n = len(o_vals)
        mean_o = sum(o_vals) / n
        mean_e = sum(e_vals) / n
        cov = sum((o - mean_o) * (e - mean_e) for o, e in zip(o_vals, e_vals)) / n
        std_o = (sum((o - mean_o) ** 2 for o in o_vals) / n) ** 0.5
        std_e = (sum((e - mean_e) ** 2 for e in e_vals) / n) ** 0.5
        corr = cov / (std_o * std_e) if std_o > 0 and std_e > 0 else 0

        # 多変量正規分布の相関行列で O-E = 0.3 を設定しているので、
        # サンプル相関は 0.1 以上であるべき
        assert corr > 0.1, f"O-E correlation {corr:.3f} is too low (expected > 0.1)"

    def test_agreeableness_mean_is_higher(self):
        """日本人ノルムでは Agreeableness の平均が 0.5 より高い。"""
        samples = self._generate_many(2000)
        a_vals = [s["A"] for s in samples]
        mean_a = sum(a_vals) / len(a_vals)
        # 設定 mean=0.58 なので、サンプル平均は 0.53 以上
        assert mean_a > 0.53, f"A mean {mean_a:.3f} is too low (expected > 0.53)"

    def test_openness_mean_is_lower(self):
        """日本人ノルム（集団主義文化）では Openness の平均が 0.5 より低い。"""
        samples = self._generate_many(2000)
        o_vals = [s["O"] for s in samples]
        mean_o = sum(o_vals) / len(o_vals)
        # 設定 mean=0.45 なので、サンプル平均は 0.49 以下
        assert mean_o < 0.49, f"O mean {mean_o:.3f} is too high (expected < 0.49)"

    def test_all_traits_in_valid_range(self):
        """全特性値が [0, 1] の範囲に収まること。"""
        samples = self._generate_many(500)
        for s in samples:
            for trait in ["O", "C", "E", "A", "N"]:
                assert 0.0 <= s[trait] <= 1.0, f"{trait}={s[trait]} is out of range"

    def test_backward_compatibility_with_config(self):
        """pop_config に big_five 設定がある場合でもエラーなく動作すること。"""
        import random
        random.seed(42)
        bf = _generate_big_five({"big_five": {"mean": 0.5, "std": 0.2}})
        for trait in ["O", "C", "E", "A", "N"]:
            assert trait in bf
            assert 0.0 <= bf[trait] <= 1.0
