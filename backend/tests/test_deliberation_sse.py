"""DeliberationEngine SSE イベント発行テスト"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_sse():
    with patch("src.app.services.cognition.deliberation.sse_manager") as mock:
        mock.publish = AsyncMock()
        yield mock


@pytest.fixture
def mock_llm():
    with patch("src.app.services.cognition.deliberation.llm_client") as mock:
        mock.call_with_retry = AsyncMock(return_value=(
            {
                "reasoning_chain": "分析→仮説→結論",
                "chosen_action": "情報収集",
                "expected_outcomes": ["知識増加"],
                "commitment_strength": 0.8,
                "belief_updates": [],
            },
            {"total_tokens": 50},
        ))
        yield mock


@pytest.fixture
def mock_record_usage():
    with patch(
        "src.app.services.cognition.deliberation.record_usage",
        new_callable=AsyncMock,
    ):
        yield


@pytest.mark.asyncio
async def test_deliberate_publishes_thinking_started(
    db_session, mock_sse, mock_llm, mock_record_usage
):
    """LLM 呼び出し前に agent_thinking_started が発行される。"""
    from src.app.services.cognition.deliberation import DeliberationEngine

    engine = DeliberationEngine()
    await engine.deliberate(
        session=db_session,
        run_id="run_1",
        agent_name="テストエージェント",
        beliefs=[],
        desires=[],
        intentions=[],
        observations=[],
        mental_models={},
    )

    calls = mock_sse.publish.call_args_list
    started_calls = [c for c in calls if c.args[1] == "agent_thinking_started"]
    assert len(started_calls) == 1
    payload = started_calls[0].args[2]
    assert payload["agent_name"] == "テストエージェント"
    assert payload["stage"] == "deliberation"


@pytest.mark.asyncio
async def test_deliberate_publishes_thinking_completed(
    db_session, mock_sse, mock_llm, mock_record_usage
):
    """LLM 呼び出し後に agent_thinking_completed が発行される。"""
    from src.app.services.cognition.deliberation import DeliberationEngine

    engine = DeliberationEngine()
    result = await engine.deliberate(
        session=db_session,
        run_id="run_1",
        agent_name="テストエージェント",
        beliefs=[],
        desires=[],
        intentions=[],
        observations=[],
        mental_models={},
    )

    calls = mock_sse.publish.call_args_list
    completed_calls = [c for c in calls if c.args[1] == "agent_thinking_completed"]
    assert len(completed_calls) == 1
    payload = completed_calls[0].args[2]
    assert payload["agent_name"] == "テストエージェント"
    assert payload["status"] == "success"
    assert "reasoning_chain" in payload


@pytest.mark.asyncio
async def test_thinking_completed_on_failure(
    db_session, mock_sse, mock_record_usage
):
    """LLM 失敗時にも agent_thinking_completed が status='failed' で発行される。"""
    with patch("src.app.services.cognition.deliberation.llm_client") as mock_llm:
        mock_llm.call_with_retry = AsyncMock(return_value=(
            "invalid_not_dict",
            {"total_tokens": 10},
        ))

        from src.app.services.cognition.deliberation import DeliberationEngine
        engine = DeliberationEngine()
        result = await engine.deliberate(
            session=db_session,
            run_id="run_1",
            agent_name="テストエージェント",
            beliefs=[],
            desires=[],
            intentions=[],
            observations=[],
            mental_models={},
        )

        calls = mock_sse.publish.call_args_list
        completed_calls = [c for c in calls if c.args[1] == "agent_thinking_completed"]
        assert len(completed_calls) == 1
        assert completed_calls[0].args[2]["status"] == "failed"
