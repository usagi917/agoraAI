"""Phase 3: ベイジアン信念更新 (Dirichlet over 5 stances)"""

from __future__ import annotations

import pytest

STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


class TestBeliefDistribution:
    def test_uniform_prior_sums_to_one(self):
        from src.app.services.society.bayesian_belief import BeliefDistribution

        belief = BeliefDistribution.uniform(STANCES)
        probs = belief.probabilities()
        assert sum(probs.values()) == pytest.approx(1.0)
        for s in STANCES:
            assert probs[s] == pytest.approx(1 / len(STANCES))

    def test_pseudo_count_concentration(self):
        from src.app.services.society.bayesian_belief import BeliefDistribution

        belief = BeliefDistribution(alpha={s: 10.0 for s in STANCES})
        # alpha 大 → 一様分布に近い、分散小
        probs = belief.probabilities()
        for s in STANCES:
            assert probs[s] == pytest.approx(0.2)


class TestUpdateBelief:
    def test_no_observation_preserves_belief(self):
        from src.app.services.society.bayesian_belief import BeliefDistribution, update_belief

        prior = BeliefDistribution.uniform(STANCES)
        posterior = update_belief(prior, observation=None)

        before = prior.probabilities()
        after = posterior.probabilities()
        for s in STANCES:
            assert after[s] == pytest.approx(before[s])

    def test_positive_observation_shifts_right(self):
        """観測 stance="賛成" を強く与えると 賛成 の確率が上がる."""
        from src.app.services.society.bayesian_belief import BeliefDistribution, update_belief

        prior = BeliefDistribution.uniform(STANCES)
        posterior = update_belief(prior, observation={"賛成": 5.0})

        before = prior.probabilities()
        after = posterior.probabilities()
        assert after["賛成"] > before["賛成"]
        # 他の stance は減る
        assert after["反対"] < before["反対"]

    def test_repeated_observations_reduce_variance(self):
        """同方向の観測を蓄積すると alpha が増えて分散が下がる."""
        from src.app.services.society.bayesian_belief import BeliefDistribution, update_belief

        belief = BeliefDistribution.uniform(STANCES)
        var_before = belief.variance()["賛成"]

        for _ in range(20):
            belief = update_belief(belief, observation={"賛成": 1.0})

        var_after = belief.variance()["賛成"]
        assert var_after < var_before

    def test_total_probability_conserved(self):
        from src.app.services.society.bayesian_belief import BeliefDistribution, update_belief

        belief = BeliefDistribution.uniform(STANCES)
        belief = update_belief(belief, observation={"中立": 3.0, "賛成": 1.0})
        assert sum(belief.probabilities().values()) == pytest.approx(1.0)
