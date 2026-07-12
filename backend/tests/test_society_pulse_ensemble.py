"""Society pulse production-path ensemble wiring tests."""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.services.society.constants import STANCE_ORDER

SWARM = dict(zip(STANCE_ORDER, (0.5, 0.2, 0.1, 0.1, 0.1), strict=True))
SINGLE = dict(zip(STANCE_ORDER, (0.1, 0.1, 0.2, 0.2, 0.4), strict=True))
UNIFORM = {stance: 0.2 for stance in STANCE_ORDER}
SINGLE_USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
ACTIVATION_USAGE = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}


async def _run_pulse(single_result, *, diagnostic_cfg=None, single_error=None):
    from src.app.services.phases.society_pulse import run_society_pulse

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_sim = MagicMock(id="sim-ensemble", population_id=None, seed=123)
    fake_agents = [
        {
            "id": f"agent-{i}",
            "agent_index": i,
            "demographics": {"occupation": "engineer", "age": 30, "region": "東京"},
            "llm_backend": "openai",
        }
        for i in range(2)
    ]
    fake_activation = {
        "responses": [
            {"stance": "賛成", "confidence": 0.8, "reason": "理由", "concern": "", "priority": ""}
            for _ in fake_agents
        ],
        "aggregation": {
            "stance_distribution": deepcopy(SWARM),
            "average_confidence": 0.75,
            "top_concerns": [],
        },
        "representatives": [{"agent_id": "agent-0"}],
        "usage": ACTIVATION_USAGE,
    }
    single_mock = AsyncMock(return_value=single_result, side_effect=single_error)

    with (
        patch(
            "src.app.services.phases.society_pulse._get_or_create_population",
            new_callable=AsyncMock,
            return_value=("pop-1", fake_agents),
        ),
        patch("src.app.services.phases.society_pulse._save_network", new_callable=AsyncMock),
        patch(
            "src.app.services.phases.society_pulse._load_population_edges",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "src.app.services.phases.society_pulse._load_selected_social_edges",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "src.app.services.phases.society_pulse.select_agents",
            new_callable=AsyncMock,
            return_value=fake_agents,
        ),
        patch(
            "src.app.services.phases.society_pulse.run_activation",
            new_callable=AsyncMock,
            return_value=fake_activation,
        ),
        patch(
            "src.app.services.phases.society_pulse.generate_persona_narratives_post_activation",
            new_callable=AsyncMock,
            return_value=fake_agents,
        ),
        patch(
            "src.app.services.phases.society_pulse.evaluate_society_simulation",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "src.app.services.phases.society_pulse.select_representatives",
            return_value=[],
        ),
        patch("src.app.services.phases.society_pulse.register_result", new_callable=AsyncMock),
        patch(
            "src.app.services.phases.society_pulse.auto_compare",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.app.services.phases.society_pulse.register_prediction_evaluation",
            new_callable=AsyncMock,
        ),
        patch("src.app.services.phases.society_pulse._diagnostic_config", return_value=diagnostic_cfg),
        patch("src.app.services.phases.society_pulse.is_enabled", return_value=True),
        patch("src.app.services.phases.society_pulse.get_ensemble_beta", return_value=0.75),
        patch(
            "src.app.services.phases.society_pulse.run_single_llm_distribution",
            new=single_mock,
        ),
        patch("src.app.services.phases.society_pulse._phase_theme_anchor") as phase_anchor,
        patch("src.app.services.phases.society_pulse.resolve_and_apply_anchor") as apply_anchor,
        patch("src.app.services.phases.society_pulse.sse_manager") as mock_sse,
    ):
        phase_anchor.return_value = (None, MagicMock(category="politics"), None, "none", [])
        apply_anchor.return_value = MagicMock(anchor_distribution=None, applied=False)
        mock_sse.publish = AsyncMock()
        result = await run_society_pulse(mock_session, mock_sim, "テスト政策")

    return result, single_mock


@pytest.mark.asyncio
async def test_valid_single_distribution_blends_production_stance_distribution():
    result, single_mock = await _run_pulse((SINGLE, SINGLE_USAGE))

    single_mock.assert_awaited_once_with("テスト政策", 123)
    assert result.aggregation["stance_distribution_pre_ensemble"] == SWARM
    assert result.aggregation["single_llm_distribution"] == SINGLE
    assert result.aggregation["ensemble_beta"] == 0.75
    assert result.aggregation["stance_distribution"] == pytest.approx(
        dict(zip(STANCE_ORDER, (0.2, 0.125, 0.175, 0.175, 0.325), strict=True))
    )
    assert result.usage == {"prompt_tokens": 11, "completion_tokens": 6, "total_tokens": 17}


@pytest.mark.asyncio
async def test_uniform_fallback_skips_blend():
    result, _ = await _run_pulse((UNIFORM, SINGLE_USAGE))

    assert result.aggregation["stance_distribution"] == SWARM
    assert result.aggregation["single_llm_distribution"] == UNIFORM
    assert result.aggregation["ensemble_skipped"] == "uniform_fallback"
    assert result.usage == {"prompt_tokens": 11, "completion_tokens": 6, "total_tokens": 17}


@pytest.mark.asyncio
async def test_single_llm_exception_skips_blend_and_pulse_completes():
    result, _ = await _run_pulse(None, single_error=RuntimeError("LLM unavailable"))

    assert result.aggregation["stance_distribution"] == SWARM
    assert result.aggregation["ensemble_skipped"] == "error"
    assert result.usage == ACTIVATION_USAGE


@pytest.mark.asyncio
async def test_diagnostic_run_does_not_call_single_llm():
    result, single_mock = await _run_pulse(
        (SINGLE, SINGLE_USAGE), diagnostic_cfg={"anchor_blend": False}
    )

    single_mock.assert_not_awaited()
    assert result.aggregation["stance_distribution"] == SWARM
    assert "single_llm_distribution" not in result.aggregation
