"""Phase 3: 粒子フィルタ (resample + ESS チェック)"""

from __future__ import annotations

import pytest

STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


class TestParticleFilter:
    def test_initialization_uniform_weights(self):
        from src.app.services.society.particle_filter import ParticleFilter

        pf = ParticleFilter(n_particles=64, stances=STANCES, seed=42)
        # 初期重みは 1/N
        weights = pf.weights()
        assert len(weights) == 64
        assert all(w == pytest.approx(1 / 64) for w in weights)

    def test_step_reweights_with_likelihood(self):
        from src.app.services.society.particle_filter import ParticleFilter

        pf = ParticleFilter(n_particles=32, stances=STANCES, seed=0)
        before = pf.weights()
        pf.step(observation={"賛成": 2.0})
        after = pf.weights()
        # 重みが変化している
        assert before != after
        # 正規化されて合計 1
        assert sum(after) == pytest.approx(1.0)

    def test_ess_drops_with_concentrated_weights(self):
        from src.app.services.society.particle_filter import ParticleFilter

        pf = ParticleFilter(n_particles=32, stances=STANCES, seed=0)
        ess_before = pf.effective_sample_size()
        # 強い観測を複数回適用 → 一部の粒子に重みが集中
        for _ in range(5):
            pf.step(observation={"賛成": 5.0})
        ess_after = pf.effective_sample_size()
        assert ess_after <= ess_before

    def test_resample_restores_uniform_weights(self):
        from src.app.services.society.particle_filter import ParticleFilter

        pf = ParticleFilter(n_particles=32, stances=STANCES, seed=0)
        pf.step(observation={"賛成": 5.0})
        pf.resample()
        weights = pf.weights()
        assert all(w == pytest.approx(1 / 32) for w in weights)

    def test_resample_triggered_by_low_ess(self):
        from src.app.services.society.particle_filter import ParticleFilter

        pf = ParticleFilter(n_particles=32, stances=STANCES, seed=0, ess_threshold=0.5)
        for _ in range(10):
            pf.step(observation={"賛成": 5.0})
        # auto resample が走った場合、ESS は閾値以上に戻っているはず
        ess_ratio = pf.effective_sample_size() / 32
        assert ess_ratio >= 0.5 - 1e-9
