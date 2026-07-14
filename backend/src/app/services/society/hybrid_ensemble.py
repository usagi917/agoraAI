"""Learn the Liquid/GPT correction weight from validated historical outcomes."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.society_result import SocietyResult
from src.app.models.validation_record import ValidationRecord
from src.app.services.society.ensemble import select_ensemble_beta

logger = logging.getLogger(__name__)

Distribution = dict[str, float]
DistributionTriplet = tuple[Distribution, Distribution, Distribution]


@dataclass(frozen=True)
class HybridShrinkage:
    shrinkage: float
    sample_count: int
    source: str


def select_hybrid_shrinkage(
    pairs: list[DistributionTriplet],
    *,
    default: float = 0.5,
    min_samples: int = 3,
) -> HybridShrinkage:
    """実測とのJSDを最小化するGPT残差の適用率を選ぶ。"""
    bounded_default = max(0.0, min(1.0, float(default)))
    if len(pairs) < max(1, min_samples):
        return HybridShrinkage(
            shrinkage=bounded_default,
            sample_count=len(pairs),
            source="conservative_default",
        )
    shrinkage = select_ensemble_beta(
        pairs,
        betas=[step / 20 for step in range(21)],
    )
    return HybridShrinkage(
        shrinkage=shrinkage,
        sample_count=len(pairs),
        source="validated_theme_history",
    )


async def load_learned_hybrid_shrinkage(
    session: AsyncSession,
    *,
    theme_category: str,
    default: float = 0.5,
    min_samples: int = 3,
) -> HybridShrinkage:
    """同一テーマ分類の検証済み履歴からハイブリッド補正率を復元する。"""
    statement = (
        select(ValidationRecord, SocietyResult)
        .join(
            SocietyResult,
            SocietyResult.simulation_id == ValidationRecord.simulation_id,
        )
        .where(
            ValidationRecord.theme_category == theme_category,
            ValidationRecord.actual_distribution.is_not(None),
            SocietyResult.layer == "activation",
        )
    )
    try:
        rows = (await session.execute(statement)).all()
    except Exception as exc:
        logger.warning("Failed to load hybrid calibration history: %s", exc)
        rows = []

    pairs: list[DistributionTriplet] = []
    for validation, society_result in rows:
        aggregation = dict((society_result.phase_data or {}).get("aggregation") or {})
        social_liquid = aggregation.get("stance_distribution_social_liquid")
        if isinstance(social_liquid, dict):
            liquid = social_liquid
            corrected = (
                aggregation.get("stance_distribution_social_hybrid_full")
                or aggregation.get("stance_distribution")
            )
        else:
            liquid = aggregation.get("stance_distribution_liquid")
            corrected = (
                aggregation.get("stance_distribution_hybrid_full")
                or aggregation.get("stance_distribution_pre_social")
                or aggregation.get("stance_distribution")
            )
        actual = validation.actual_distribution
        if isinstance(liquid, dict) and isinstance(corrected, dict) and isinstance(actual, dict):
            pairs.append((liquid, corrected, actual))

    return select_hybrid_shrinkage(
        pairs,
        default=default,
        min_samples=min_samples,
    )
