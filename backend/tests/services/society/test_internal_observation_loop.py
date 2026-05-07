"""Wave A: 内部観測ループ — Phase 5 cascade と Phase 3 ベイジアン更新の橋渡し.

外部ニュースを使わずに、agent 同士の発言を Bayesian observation として
ParticleFilter に流し込んで、信念分布を更新する。
"""

from __future__ import annotations

import pytest

STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


def _resp(agent_id: int, stance: str, confidence: float = 0.7) -> dict:
    return {"agent_id": agent_id, "stance": stance, "confidence": confidence}


class TestRoundToObservation:
    def test_counts_each_stance(self):
        from src.app.services.society.internal_observation_loop import round_to_observation

        round_snap = [
            _resp(0, "賛成"),
            _resp(1, "賛成"),
            _resp(2, "反対"),
        ]
        obs = round_to_observation(round_snap)
        assert obs["賛成"] == pytest.approx(2.0)
        assert obs["反対"] == pytest.approx(1.0)
        assert "中立" not in obs or obs["中立"] == 0.0

    def test_confidence_weighting(self):
        """confidence weight=True で重み付き観測を作る."""
        from src.app.services.society.internal_observation_loop import round_to_observation

        round_snap = [
            _resp(0, "賛成", confidence=0.9),
            _resp(1, "賛成", confidence=0.1),
        ]
        obs = round_to_observation(round_snap, weight_by_confidence=True)
        assert obs["賛成"] == pytest.approx(1.0, abs=1e-6)  # 0.9 + 0.1

    def test_empty_round_returns_empty_dict(self):
        from src.app.services.society.internal_observation_loop import round_to_observation

        assert round_to_observation([]) == {}


class TestNeighborObservations:
    def test_neighbor_filter_uses_only_neighbors(self):
        from src.app.services.society.internal_observation_loop import neighbor_observation

        round_snap = [
            _resp(0, "賛成"),
            _resp(1, "反対"),
            _resp(2, "賛成"),
            _resp(3, "反対"),
        ]
        edges = [(0, 1), (0, 2)]  # agent 0 の隣接は {1, 2}
        obs = neighbor_observation(round_snap, edges, target_agent_id=0)
        # 隣接 agent (1, 2) の発言のみ観測
        assert obs.get("賛成", 0.0) == pytest.approx(1.0)
        assert obs.get("反対", 0.0) == pytest.approx(1.0)
        # agent 3 は隣接ではないので含まれない
        # 観測総量は 2.0
        assert sum(obs.values()) == pytest.approx(2.0)

    def test_isolated_agent_returns_empty(self):
        from src.app.services.society.internal_observation_loop import neighbor_observation

        round_snap = [_resp(0, "賛成"), _resp(1, "反対")]
        obs = neighbor_observation(round_snap, edges=[], target_agent_id=0)
        assert obs == {}


class TestIntegrateCascadeWithBelief:
    def test_runs_one_step_per_round(self):
        """cascade のラウンド数だけ particle_filter.step() が呼ばれる."""
        from src.app.services.society.internal_observation_loop import (
            integrate_cascade_with_belief,
        )
        from src.app.services.society.particle_filter import ParticleFilter

        pf = ParticleFilter(n_particles=16, stances=STANCES, seed=0)
        cascade = [
            [_resp(0, "中立")],            # round 0 (初期)
            [_resp(0, "賛成")],            # round 1
            [_resp(0, "賛成")],            # round 2
        ]
        aggregate = integrate_cascade_with_belief(cascade, pf)

        # aggregate は確率分布
        assert sum(aggregate.values()) == pytest.approx(1.0)
        # 賛成の観測が 2 ラウンド入ったので 賛成 が高くなる
        assert aggregate["賛成"] > aggregate["反対"]

    def test_skips_initial_round(self):
        """先頭 (round 0 = 初期) は prior として扱い、observation には流さない."""
        from src.app.services.society.internal_observation_loop import (
            integrate_cascade_with_belief,
        )
        from src.app.services.society.particle_filter import ParticleFilter

        pf = ParticleFilter(n_particles=16, stances=STANCES, seed=0)
        cascade = [
            # 初期 round が 賛成 100% でも、観測には流さない設計
            [_resp(0, "賛成"), _resp(1, "賛成")],
        ]
        before = pf.aggregate_distribution()
        integrate_cascade_with_belief(cascade, pf)
        after = pf.aggregate_distribution()
        # 観測は流れていないので分布はほぼ変わらない
        assert after["賛成"] == pytest.approx(before["賛成"], abs=0.01)

    def test_empty_cascade_does_not_raise(self):
        from src.app.services.society.internal_observation_loop import (
            integrate_cascade_with_belief,
        )
        from src.app.services.society.particle_filter import ParticleFilter

        pf = ParticleFilter(n_particles=8, stances=STANCES, seed=0)
        result = integrate_cascade_with_belief([], pf)
        # 空でも例外なく aggregate を返す
        assert sum(result.values()) == pytest.approx(1.0)

    def test_consensus_cascade_concentrates_belief(self):
        """全 agent が同じ stance を発言し続けると、その stance に信念が集中する."""
        from src.app.services.society.internal_observation_loop import (
            integrate_cascade_with_belief,
        )
        from src.app.services.society.particle_filter import ParticleFilter

        pf = ParticleFilter(n_particles=32, stances=STANCES, seed=0)
        # 5 ラウンド全員 賛成
        cascade = [[_resp(i, "賛成") for i in range(10)] for _ in range(6)]
        aggregate = integrate_cascade_with_belief(cascade, pf)

        # 賛成 が他の stance より圧倒的に高い
        assert aggregate["賛成"] > 0.5
        for stance in STANCES:
            if stance != "賛成":
                assert aggregate[stance] < aggregate["賛成"]


class TestObservationStrengthAttenuation:
    """単一 round が信念を反転させない (prior 強度の確認)."""

    def test_single_round_does_not_flip_strong_prior(self):
        from src.app.services.society.bayesian_belief import BeliefDistribution
        from src.app.services.society.internal_observation_loop import (
            integrate_cascade_with_belief,
        )
        from src.app.services.society.particle_filter import ParticleFilter

        # 強い prior: 反対 90%
        pf = ParticleFilter(n_particles=32, stances=STANCES, seed=0)
        # 全粒子に強い 反対 prior を上書き
        pf._particles = [
            BeliefDistribution(alpha={"賛成": 1.0, "条件付き賛成": 1.0, "中立": 1.0,
                                      "条件付き反対": 1.0, "反対": 50.0})
            for _ in range(32)
        ]
        cascade = [
            [_resp(0, "中立")],
            [_resp(0, "賛成")],  # 1 ラウンド 賛成 観測
        ]
        aggregate = integrate_cascade_with_belief(cascade, pf)
        # 反対 が依然優勢 (1 round で反転しない)
        assert aggregate["反対"] > aggregate["賛成"]
