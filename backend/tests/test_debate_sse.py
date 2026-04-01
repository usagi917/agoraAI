"""DebateProtocol SSE イベント発行テスト"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_sse():
    with patch("src.app.services.communication.debate_protocol.sse_manager") as mock:
        mock.publish_debate_result = AsyncMock()
        yield mock


@pytest.fixture
def mock_llm():
    """DebateProtocol 用 LLM モック: claims→counters→rebuttals→judgeの順に応答。"""
    call_count = {"n": 0}

    async def _side_effect(**kwargs):
        call_count["n"] += 1
        n = call_count["n"]
        if n == 1:  # claims
            return (
                {"claims": [
                    {"agent_id": "a1", "claim": "主張A", "evidence": "根拠A", "strength": 0.8},
                    {"agent_id": "a2", "claim": "主張B", "evidence": "根拠B", "strength": 0.7},
                ]},
                {"total_tokens": 30},
            )
        elif n == 2:  # counters
            return (
                {"counters": [
                    {"agent_id": "a2", "target_agent_id": "a1", "claim": "反論", "evidence": "反証", "strength": 0.6},
                ]},
                {"total_tokens": 20},
            )
        elif n == 3:  # rebuttals
            return (
                {"rebuttals": [
                    {"agent_id": "a1", "claim": "再反論", "evidence": "再根拠", "strength": 0.7},
                ]},
                {"total_tokens": 20},
            )
        else:  # judge
            return (
                {
                    "winner_agent_id": "a1",
                    "winning_argument": "主張Aが優勢",
                    "reasoning": "根拠の質が高い",
                    "consensus": False,
                    "argument_scores": [],
                },
                {"total_tokens": 25},
            )

    with patch("src.app.services.communication.debate_protocol.llm_client") as mock:
        mock.call_with_retry = AsyncMock(side_effect=_side_effect)
        yield mock


@pytest.fixture
def mock_record_usage():
    with patch(
        "src.app.services.communication.debate_protocol.record_usage",
        new_callable=AsyncMock,
    ):
        yield


@pytest.mark.asyncio
async def test_debate_result_published_after_judging(
    db_session, mock_sse, mock_llm, mock_record_usage,
):
    """run_debate() 完了後に publish_debate_result が呼ばれる。"""
    from src.app.services.communication.debate_protocol import DebateProtocol
    from src.app.services.communication.conversation import ConversationChannel
    from src.app.services.communication.message_bus import MessageBus

    protocol = DebateProtocol()
    channel = ConversationChannel(
        channel_type="negotiation",
        participants={"a1", "a2"},
        topic="テスト議題",
    )
    participants = [
        {"id": "a1", "name": "Agent A", "role": "expert", "goals": ["目標A"]},
        {"id": "a2", "name": "Agent B", "role": "citizen", "goals": ["目標B"]},
    ]
    message_bus = MessageBus()

    result = await protocol.run_debate(
        session=db_session,
        run_id="run_1",
        channel=channel,
        participants=participants,
        topic="テスト議題",
        message_bus=message_bus,
        round_number=1,
    )

    mock_sse.publish_debate_result.assert_called_once()
    call_args = mock_sse.publish_debate_result.call_args
    assert call_args.args[0] == "run_1"
    data = call_args.args[1]
    assert data["topic"] == "テスト議題"
    assert data["winner_agent_id"] == "a1"
    assert "judge_reasoning" in data
    assert "arguments" in data
    assert len(data["arguments"]) > 0


@pytest.mark.asyncio
async def test_debate_result_payload_structure(
    db_session, mock_sse, mock_llm, mock_record_usage,
):
    """debate_result ペイロードの構造が正しい。"""
    from src.app.services.communication.debate_protocol import DebateProtocol
    from src.app.services.communication.conversation import ConversationChannel
    from src.app.services.communication.message_bus import MessageBus

    protocol = DebateProtocol()
    channel = ConversationChannel(
        channel_type="negotiation",
        participants={"a1", "a2"},
        topic="議題",
    )
    participants = [
        {"id": "a1", "name": "A", "role": "expert", "goals": []},
        {"id": "a2", "name": "B", "role": "citizen", "goals": []},
    ]

    await protocol.run_debate(
        session=db_session,
        run_id="run_1",
        channel=channel,
        participants=participants,
        topic="議題",
        message_bus=MessageBus(),
        round_number=1,
    )

    data = mock_sse.publish_debate_result.call_args.args[1]
    assert "channel_id" in data
    assert "consensus_reached" in data
    # 各 argument に必要なフィールドがある
    for arg in data["arguments"]:
        assert "agent_id" in arg
        assert "claim" in arg
        assert "type" in arg
