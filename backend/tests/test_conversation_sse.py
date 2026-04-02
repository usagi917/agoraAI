"""ConversationManager SSE イベント発行テスト"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_sse():
    with patch("src.app.services.communication.conversation.sse_manager") as mock:
        mock.publish_conversation_event = AsyncMock()
        yield mock


@pytest.mark.asyncio
async def test_initiate_conversation_publishes_started(mock_sse):
    """initiate_conversation() が conversation_started を発行する。"""
    from src.app.services.communication.conversation import ConversationManager

    mgr = ConversationManager()
    channel = await mgr.initiate_conversation(
        run_id="run_1",
        initiator_id="agent_1",
        participant_ids=["agent_2"],
        topic="テスト議題",
        channel_type="direct",
    )

    mock_sse.publish_conversation_event.assert_called_once()
    call_args = mock_sse.publish_conversation_event.call_args
    assert call_args.args[0] == "run_1"
    assert call_args.args[1] == "started"
    data = call_args.args[2]
    assert data["channel_id"] == channel.id
    assert data["topic"] == "テスト議題"
    assert data["participant_count"] == 2
    assert data["initiator_id"] == "agent_1"
    assert set(data["participants"]) == {"agent_1", "agent_2"}


@pytest.mark.asyncio
async def test_advance_turn_publishes_turn_advanced(mock_sse):
    """advance_turn() が conversation_turn_advanced を発行する。"""
    from src.app.services.communication.conversation import ConversationManager

    mgr = ConversationManager()
    channel = await mgr.initiate_conversation(
        run_id="run_1",
        initiator_id="agent_1",
        participant_ids=["agent_2"],
        topic="テスト",
    )
    mock_sse.publish_conversation_event.reset_mock()

    await mgr.advance_turn("run_1", channel.id)

    mock_sse.publish_conversation_event.assert_called_once()
    call_args = mock_sse.publish_conversation_event.call_args
    assert call_args.args[1] == "turn_advanced"
    data = call_args.args[2]
    assert data["channel_id"] == channel.id
    assert data["current_turn"] == 1


@pytest.mark.asyncio
async def test_conclude_channel_publishes_concluded(mock_sse):
    """conclude_channel() が conversation_concluded を発行する。"""
    from src.app.services.communication.conversation import ConversationManager

    mgr = ConversationManager()
    channel = await mgr.initiate_conversation(
        run_id="run_1",
        initiator_id="agent_1",
        participant_ids=["agent_2"],
        topic="テスト",
    )
    mock_sse.publish_conversation_event.reset_mock()

    await mgr.conclude_channel("run_1", channel.id)

    mock_sse.publish_conversation_event.assert_called_once()
    call_args = mock_sse.publish_conversation_event.call_args
    assert call_args.args[1] == "concluded"
    data = call_args.args[2]
    assert data["channel_id"] == channel.id
