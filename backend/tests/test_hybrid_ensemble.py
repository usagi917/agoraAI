"""Observed-outcome learning for Liquid/GPT hybrid correction weight."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.app.services.society.hybrid_ensemble import (
    load_learned_hybrid_shrinkage,
    select_hybrid_shrinkage,
)


def test_selects_gpt_correction_only_when_it_improves_observed_accuracy() -> None:
    local = {"賛成": 0.8, "反対": 0.2}
    corrected = {"賛成": 0.3, "反対": 0.7}
    actual = {"賛成": 0.35, "反対": 0.65}

    result = select_hybrid_shrinkage([(local, corrected, actual)] * 4)

    assert result.sample_count == 4
    assert result.source == "validated_theme_history"
    assert result.shrinkage > 0.8


def test_defaults_to_conservative_half_weight_without_enough_actuals() -> None:
    result = select_hybrid_shrinkage([], default=0.5, min_samples=3)

    assert result.shrinkage == 0.5
    assert result.sample_count == 0
    assert result.source == "conservative_default"


@pytest.mark.asyncio
async def test_loader_uses_only_rows_with_liquid_corrected_and_actual_distributions() -> None:
    validation = SimpleNamespace(
        actual_distribution={"賛成": 0.4, "反対": 0.6},
    )
    society_result = SimpleNamespace(
        phase_data={
            "aggregation": {
                "stance_distribution_liquid": {"賛成": 0.7, "反対": 0.3},
                "stance_distribution_hybrid_full": {"賛成": 0.95, "反対": 0.05},
                "stance_distribution_social_liquid": {"賛成": 0.8, "反対": 0.2},
                "stance_distribution_social_hybrid_full": {"賛成": 0.45, "反対": 0.55},
                "stance_distribution": {"賛成": 0.9, "反対": 0.1},
            }
        }
    )
    query_result = MagicMock()
    query_result.all.return_value = [(validation, society_result)] * 3
    session = MagicMock()
    session.execute = AsyncMock(return_value=query_result)

    result = await load_learned_hybrid_shrinkage(session, theme_category="politics")

    assert result.sample_count == 3
    assert result.shrinkage > 0.5
