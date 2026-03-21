"""人口生成サービスのテスト: 分布特性、スキーマ検証"""

import pytest

from src.app.services.society.population_generator import (
    generate_population,
    generate_agent_profile,
)


class TestGenerateAgentProfile:
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


class TestGeneratePopulation:
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
    async def test_llm_backend_assignment(self):
        agents = await generate_population("pop", count=200, seed=42)
        backends = set(a["llm_backend"] for a in agents)
        # Should assign at least 2 different backends
        assert len(backends) >= 2
