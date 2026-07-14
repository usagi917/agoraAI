"""Single-LLM と swarm のスタンス分布アンサンブル。"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from src.app.config import settings
from src.app.evaluation.metrics import JSDMetric
from src.app.services.society.constants import STANCE_ORDER

logger = logging.getLogger(__name__)

DEFAULT_SINGLE_LLM_BETA = 0.85

Distribution = dict[str, float]
DistributionPair = tuple[Distribution, Distribution, Distribution]


def blend_distributions(
    swarm: Distribution,
    single: Distribution,
    beta: float,
) -> Distribution:
    """単一LLMを beta、swarmを 1-beta として凸結合する。"""
    if not 0.0 <= beta <= 1.0:
        raise ValueError("beta must be between 0 and 1")

    blended = {
        stance: beta * single.get(stance, 0.0) + (1.0 - beta) * swarm.get(stance, 0.0)
        for stance in STANCE_ORDER
    }
    total = sum(blended.values())
    if total <= 0:
        return {stance: 1.0 / len(STANCE_ORDER) for stance in STANCE_ORDER}
    return {stance: value / total for stance, value in blended.items()}


def is_uniform_fallback(dist: Distribution, tol: float = 1e-6) -> bool:
    """診断baselineが失敗時に返す5分類一様分布かを判定する。"""
    expected = 1.0 / len(STANCE_ORDER)
    return all(
        stance in dist and abs(dist[stance] - expected) <= tol
        for stance in STANCE_ORDER
    )


def select_ensemble_beta(
    pairs: Sequence[DistributionPair],
    betas: Iterable[float] | None = None,
) -> float:
    """平均JSDを最小化する beta をグリッド探索する。"""
    candidates = list(betas) if betas is not None else [step / 20 for step in range(21)]
    if not candidates:
        raise ValueError("betas must not be empty")
    if not pairs:
        raise ValueError("pairs must not be empty")

    metric = JSDMetric()

    def mean_jsd(beta: float) -> float:
        scores = [
            metric.compute(
                predicted=blend_distributions(swarm, single, beta),
                observed=truth,
            )["score"]
            for swarm, single, truth in pairs
        ]
        return sum(scores) / len(scores)

    return min(candidates, key=mean_jsd)


def get_ensemble_beta() -> float:
    """population_mix設定から単一LLMの混合比を取得する。"""
    try:
        config = settings.load_population_mix_config()
        return float(config.get("ensemble", {}).get("single_llm_beta", DEFAULT_SINGLE_LLM_BETA))
    except Exception as exc:
        logger.warning("Failed to load ensemble beta: %s", exc)
        return DEFAULT_SINGLE_LLM_BETA
