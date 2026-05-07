"""Phase 3: シーケンシャル Monte Carlo (粒子フィルタ).

各粒子は BeliefDistribution. 観測ごとに尤度に応じて重みを更新し、
ESS が閾値を下回ったら自動 resample (systematic resampling).
"""

from __future__ import annotations

import math
import random
from typing import Iterable

from src.app.services.society.bayesian_belief import BeliefDistribution, update_belief


class ParticleFilter:
    def __init__(
        self,
        n_particles: int,
        stances: Iterable[str],
        seed: int = 0,
        ess_threshold: float = 0.5,
    ) -> None:
        if n_particles <= 0:
            raise ValueError("n_particles must be > 0")
        self.n_particles = n_particles
        self.stances = list(stances)
        self.ess_threshold = ess_threshold
        self._rng = random.Random(seed)
        # 初期粒子: 一様 prior に小さなノイズを加えて生成
        self._particles: list[BeliefDistribution] = []
        for _ in range(n_particles):
            alpha = {s: 1.0 + self._rng.uniform(-0.1, 0.1) for s in self.stances}
            self._particles.append(BeliefDistribution(alpha=alpha))
        self._weights: list[float] = [1.0 / n_particles] * n_particles

    def weights(self) -> list[float]:
        return list(self._weights)

    def particles(self) -> list[BeliefDistribution]:
        return list(self._particles)

    def effective_sample_size(self) -> float:
        s = sum(w * w for w in self._weights)
        return 1.0 / s if s > 0 else 0.0

    def step(self, observation: dict[str, float] | None) -> None:
        """全粒子を観測で更新し、尤度で重みを再正規化. ESS 低下時は auto resample."""
        new_particles: list[BeliefDistribution] = []
        new_weights: list[float] = []
        for particle, weight in zip(self._particles, self._weights, strict=True):
            posterior = update_belief(particle, observation)
            likelihood = self._observation_likelihood(particle, observation)
            new_weights.append(weight * likelihood)
            new_particles.append(posterior)

        total = sum(new_weights)
        if total > 0:
            self._weights = [w / total for w in new_weights]
        else:
            self._weights = [1.0 / self.n_particles] * self.n_particles
        self._particles = new_particles

        # ESS チェック
        ess_ratio = self.effective_sample_size() / self.n_particles
        if ess_ratio < self.ess_threshold:
            self.resample()

    def resample(self) -> None:
        """systematic resampling: 重みに比例して粒子を再標本し、重みを 1/N に戻す."""
        n = self.n_particles
        positions = [(self._rng.random() + i) / n for i in range(n)]
        cumulative = []
        running = 0.0
        for w in self._weights:
            running += w
            cumulative.append(running)

        new_particles: list[BeliefDistribution] = []
        idx = 0
        for pos in positions:
            while idx < n - 1 and pos > cumulative[idx]:
                idx += 1
            new_particles.append(BeliefDistribution(alpha=dict(self._particles[idx].alpha)))
        self._particles = new_particles
        self._weights = [1.0 / n] * n

    def aggregate_distribution(self) -> dict[str, float]:
        """全粒子の重み付き平均で代表分布を出す."""
        result: dict[str, float] = {s: 0.0 for s in self.stances}
        for particle, weight in zip(self._particles, self._weights, strict=True):
            probs = particle.probabilities()
            for s in self.stances:
                result[s] += weight * probs.get(s, 0.0)
        total = sum(result.values())
        if total > 0:
            return {k: v / total for k, v in result.items()}
        return result

    @staticmethod
    def _observation_likelihood(
        particle: BeliefDistribution,
        observation: dict[str, float] | None,
    ) -> float:
        if not observation:
            return 1.0
        probs = particle.probabilities()
        # log p(obs|theta) = sum_k count_k * log p_k, exp for likelihood
        log_lik = 0.0
        for stance, count in observation.items():
            p = probs.get(stance, 1e-12)
            if p <= 0:
                p = 1e-12
            log_lik += count * math.log(p)
        return math.exp(log_lik)
