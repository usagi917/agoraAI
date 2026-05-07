"""Phase 2: population_drift のテスト"""

from __future__ import annotations


def _agent(idx: int, age: int = 30, **overrides):
    base = {
        "agent_id": idx,
        "age": age,
        "stance": "中立",
        "confidence": 0.5,
    }
    base.update(overrides)
    return base


class TestAgeAdvance:
    def test_age_advance_cohort_adds_years(self):
        from src.app.services.society.population_drift import age_advance_cohort

        agents = [_agent(0, age=30), _agent(1, age=65)]
        advanced = age_advance_cohort(agents, delta_days=365)

        assert advanced[0]["age"] == 31
        assert advanced[1]["age"] == 66

    def test_age_advance_partial_year(self):
        from src.app.services.society.population_drift import age_advance_cohort

        agents = [_agent(0, age=30)]
        advanced = age_advance_cohort(agents, delta_days=180)

        # 半年程度では age 整数は 30 のまま (端数切捨)
        assert advanced[0]["age"] == 30

    def test_age_advance_three_years(self):
        from src.app.services.society.population_drift import age_advance_cohort

        agents = [_agent(0, age=30)]
        advanced = age_advance_cohort(agents, delta_days=1095)

        assert advanced[0]["age"] == 33


class TestBirthDeath:
    def test_apply_birth_death_removes_old(self):
        from src.app.services.society.population_drift import apply_birth_death

        agents = [_agent(0, age=30), _agent(1, age=95)]
        new_agents = apply_birth_death(agents, delta_days=365, mortality_age=85, birth_rate=0.0, seed=42)

        ages = [a["age"] for a in new_agents]
        # 95 歳の agent は除外
        assert 95 not in ages

    def test_apply_birth_death_adds_new(self):
        from src.app.services.society.population_drift import apply_birth_death

        agents = [_agent(0, age=30)]
        new_agents = apply_birth_death(agents, delta_days=365, mortality_age=200, birth_rate=2.0, seed=0)

        # birth_rate=2.0 で大量参入 (delta_days=365 → 2 人/年)
        assert len(new_agents) > len(agents)

    def test_apply_birth_death_is_deterministic_with_seed(self):
        from src.app.services.society.population_drift import apply_birth_death

        agents = [_agent(0, age=30)]
        a = apply_birth_death(agents, delta_days=365, mortality_age=200, birth_rate=1.0, seed=42)
        b = apply_birth_death(agents, delta_days=365, mortality_age=200, birth_rate=1.0, seed=42)
        assert len(a) == len(b)
