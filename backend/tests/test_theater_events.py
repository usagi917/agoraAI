"""Tests for theater_events module: claim_made, stance_shifted, alliance_formed,
market_moved, and decision_locked SSE event extraction and emission."""

import pytest
from unittest.mock import AsyncMock, patch

from src.app.services.theater_events import (
    stance_to_numeric,
    emit_claim_made,
    emit_claims_from_round,
    emit_stance_shifted,
    detect_and_emit_stance_shifts,
    emit_alliance_formed,
    detect_and_emit_alliances,
    emit_market_moved,
    detect_and_emit_market_move,
    emit_decision_locked,
    emit_decision_from_synthesis,
    process_round_theater_events,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _make_arg(pid: int, position: str, argument: str = "some argument", belief_update: str = "") -> dict:
    return {
        "participant_index": pid,
        "position": position,
        "argument": argument,
        "belief_update": belief_update,
    }


@pytest.fixture
def mock_publish():
    with patch("src.app.services.theater_events.sse_manager") as m:
        m.publish = AsyncMock()
        yield m.publish


# ── stance_to_numeric ────────────────────────────────────────────────

class TestStanceToNumeric:
    def test_known_stances(self):
        assert stance_to_numeric("賛成") == 1.0
        assert stance_to_numeric("条件付き賛成") == 0.7
        assert stance_to_numeric("中立") == 0.5
        assert stance_to_numeric("条件付き反対") == 0.3
        assert stance_to_numeric("反対") == 0.0

    def test_unknown_stance_defaults_to_0_5(self):
        assert stance_to_numeric("unknown") == 0.5
        assert stance_to_numeric("") == 0.5

    def test_partial_match(self):
        # Contains a known key
        assert stance_to_numeric("やや賛成") == 1.0


# ── claim_made ───────────────────────────────────────────────────────

class TestClaimMade:
    @pytest.mark.asyncio
    async def test_emit_claim_made(self, mock_publish):
        await emit_claim_made("run-1", 0, "test claim", "賛成", 0.8)
        mock_publish.assert_called_once_with("run-1", "claim_made", {
            "agent_id": 0,
            "claim_text": "test claim",
            "stance": "賛成",
            "confidence": 0.8,
        })

    @pytest.mark.asyncio
    async def test_emit_claims_from_round(self, mock_publish):
        args = [
            _make_arg(0, "賛成", "I support this"),
            _make_arg(1, "反対", "I oppose this"),
            _make_arg(2, "中立", ""),  # empty argument -> skipped
        ]
        await emit_claims_from_round("run-1", args)
        assert mock_publish.call_count == 2

    @pytest.mark.asyncio
    async def test_emit_claims_skips_empty(self, mock_publish):
        args = [_make_arg(0, "賛成", "")]
        await emit_claims_from_round("run-1", args)
        mock_publish.assert_not_called()


# ── stance_shifted ───────────────────────────────────────────────────

class TestStanceShifted:
    @pytest.mark.asyncio
    async def test_emit_stance_shifted(self, mock_publish):
        await emit_stance_shifted("run-1", 0, 0.5, 1.0, "convinced by data")
        mock_publish.assert_called_once_with("run-1", "stance_shifted", {
            "agent_id": 0,
            "from_stance": 0.5,
            "to_stance": 1.0,
            "reason": "convinced by data",
        })

    @pytest.mark.asyncio
    async def test_detect_shifts_above_threshold(self, mock_publish):
        prev = [_make_arg(0, "中立"), _make_arg(1, "反対")]
        curr = [_make_arg(0, "賛成"), _make_arg(1, "反対")]  # agent 0 shifted

        shifts = await detect_and_emit_stance_shifts("run-1", prev, curr)
        assert len(shifts) == 1
        assert shifts[0]["agent_id"] == 0
        assert shifts[0]["from_stance"] == 0.5  # 中立
        assert shifts[0]["to_stance"] == 1.0  # 賛成

    @pytest.mark.asyncio
    async def test_detect_shifts_below_threshold_ignored(self, mock_publish):
        # 条件付き賛成(0.7) -> 賛成(1.0) = delta 0.3, above threshold -> fires
        # But 中立(0.5) -> same 中立(0.5) = delta 0, below -> ignored
        prev = [_make_arg(0, "中立")]
        curr = [_make_arg(0, "中立")]

        shifts = await detect_and_emit_stance_shifts("run-1", prev, curr)
        assert len(shifts) == 0
        mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_detect_shifts_uses_belief_update_as_reason(self, mock_publish):
        prev = [_make_arg(0, "反対")]
        curr = [_make_arg(0, "賛成", belief_update="説得された")]

        shifts = await detect_and_emit_stance_shifts("run-1", prev, curr)
        assert len(shifts) == 1
        assert shifts[0]["reason"] == "説得された"

    @pytest.mark.asyncio
    async def test_detect_shifts_default_reason(self, mock_publish):
        prev = [_make_arg(0, "反対")]
        curr = [_make_arg(0, "賛成", belief_update="")]

        shifts = await detect_and_emit_stance_shifts("run-1", prev, curr)
        assert shifts[0]["reason"] == "stance changed"

    @pytest.mark.asyncio
    async def test_detect_shifts_skips_missing_agents(self, mock_publish):
        prev = [_make_arg(0, "反対")]
        curr = [_make_arg(1, "賛成")]  # agent 1 not in prev

        shifts = await detect_and_emit_stance_shifts("run-1", prev, curr)
        assert len(shifts) == 0

    @pytest.mark.asyncio
    async def test_detect_shifts_skips_pid_negative_one(self, mock_publish):
        prev = [_make_arg(-1, "反対")]
        curr = [_make_arg(-1, "賛成")]

        shifts = await detect_and_emit_stance_shifts("run-1", prev, curr)
        assert len(shifts) == 0


# ── alliance_formed ──────────────────────────────────────────────────

class TestAllianceFormed:
    @pytest.mark.asyncio
    async def test_emit_alliance_formed(self, mock_publish):
        await emit_alliance_formed("run-1", [0, 1], 0.85, 0.5)
        mock_publish.assert_called_once_with("run-1", "alliance_formed", {
            "agent_ids": [0, 1],
            "stance": 0.85,
            "strength": 0.5,
        })

    @pytest.mark.asyncio
    async def test_detect_two_adjacent_agents(self, mock_publish):
        # Two agents both 賛成(1.0) -> alliance
        args = [_make_arg(0, "賛成"), _make_arg(1, "賛成")]
        alliances = await detect_and_emit_alliances("run-1", args)
        assert len(alliances) == 1
        assert set(alliances[0]["agent_ids"]) == {0, 1}

    @pytest.mark.asyncio
    async def test_detect_no_alliance_when_far_apart(self, mock_publish):
        # 賛成(1.0) and 反対(0.0) -> no alliance
        args = [_make_arg(0, "賛成"), _make_arg(1, "反対")]
        alliances = await detect_and_emit_alliances("run-1", args)
        assert len(alliances) == 0

    @pytest.mark.asyncio
    async def test_detect_multiple_clusters(self, mock_publish):
        # Cluster 1: agents 0, 1 at 賛成(1.0)
        # Cluster 2: agents 2, 3 at 反対(0.0)
        # Agent 4 alone at 中立(0.5)
        args = [
            _make_arg(0, "賛成"),
            _make_arg(1, "賛成"),
            _make_arg(2, "反対"),
            _make_arg(3, "反対"),
            _make_arg(4, "中立"),
        ]
        alliances = await detect_and_emit_alliances("run-1", args)
        assert len(alliances) == 2

    @pytest.mark.asyncio
    async def test_cap_at_50_percent(self, mock_publish):
        """When all agents have the same stance, cap coalition at 50% of total."""
        args = [_make_arg(i, "賛成") for i in range(6)]
        alliances = await detect_and_emit_alliances("run-1", args)
        assert len(alliances) == 1
        assert len(alliances[0]["agent_ids"]) == 3  # 50% of 6

    @pytest.mark.asyncio
    async def test_cap_at_50_percent_odd_number(self, mock_publish):
        """For 5 agents all same stance, cap at floor(5/2)=2."""
        args = [_make_arg(i, "賛成") for i in range(5)]
        alliances = await detect_and_emit_alliances("run-1", args)
        assert len(alliances) == 1
        assert len(alliances[0]["agent_ids"]) == 2  # floor(5/2)

    @pytest.mark.asyncio
    async def test_cap_at_50_percent_two_agents(self, mock_publish):
        """With exactly 2 agents same stance, max_coalition = 2 (special case)."""
        args = [_make_arg(0, "賛成"), _make_arg(1, "賛成")]
        alliances = await detect_and_emit_alliances("run-1", args)
        assert len(alliances) == 1
        assert len(alliances[0]["agent_ids"]) == 2

    @pytest.mark.asyncio
    async def test_single_agent_no_alliance(self, mock_publish):
        args = [_make_arg(0, "賛成")]
        alliances = await detect_and_emit_alliances("run-1", args)
        assert len(alliances) == 0

    @pytest.mark.asyncio
    async def test_proximity_threshold_boundary(self, mock_publish):
        """Agents with stance delta exactly at threshold should NOT cluster."""
        # 賛成(1.0) and 条件付き賛成(0.7) -> delta 0.3 >= 0.15, separate
        args = [_make_arg(0, "賛成"), _make_arg(1, "条件付き賛成")]
        alliances = await detect_and_emit_alliances("run-1", args)
        assert len(alliances) == 0

    @pytest.mark.asyncio
    async def test_dedup_agents_from_sub_rounds(self, mock_publish):
        """Duplicate participant_index entries are deduplicated (last wins)."""
        args = [
            _make_arg(0, "中立"),      # first occurrence
            _make_arg(1, "賛成"),
            _make_arg(0, "賛成"),      # updated stance for agent 0
        ]
        alliances = await detect_and_emit_alliances("run-1", args)
        # Both agents now at 賛成(1.0) -> alliance
        assert len(alliances) == 1
        assert set(alliances[0]["agent_ids"]) == {0, 1}


# ── market_moved ─────────────────────────────────────────────────────

class TestMarketMoved:
    @pytest.mark.asyncio
    async def test_emit_market_moved(self, mock_publish):
        await emit_market_moved("run-1", "mkt-1", 0.5, 0.6, "new data")
        mock_publish.assert_called_once_with("run-1", "market_moved", {
            "market_id": "mkt-1",
            "old_prob": 0.5,
            "new_prob": 0.6,
            "driver": "new data",
        })

    @pytest.mark.asyncio
    async def test_detect_above_threshold(self, mock_publish):
        emitted = await detect_and_emit_market_move("run-1", "mkt-1", 0.5, 0.56, "shift")
        assert emitted is True
        mock_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_detect_below_threshold(self, mock_publish):
        emitted = await detect_and_emit_market_move("run-1", "mkt-1", 0.5, 0.54, "minor")
        assert emitted is False
        mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_detect_exact_threshold(self, mock_publish):
        emitted = await detect_and_emit_market_move("run-1", "mkt-1", 0.5, 0.55, "edge")
        assert emitted is True

    @pytest.mark.asyncio
    async def test_detect_negative_shift(self, mock_publish):
        emitted = await detect_and_emit_market_move("run-1", "mkt-1", 0.6, 0.5, "drop")
        assert emitted is True


# ── decision_locked ──────────────────────────────────────────────────

class TestDecisionLocked:
    @pytest.mark.asyncio
    async def test_emit_decision_locked(self, mock_publish):
        await emit_decision_locked("run-1", "Go with plan A", 0.85, 2)
        mock_publish.assert_called_once_with("run-1", "decision_locked", {
            "decision_text": "Go with plan A",
            "confidence": 0.85,
            "dissent_count": 2,
        })

    @pytest.mark.asyncio
    async def test_emit_from_synthesis(self, mock_publish):
        brief = {
            "decision_summary": "Launch the product",
            "recommendation": "Go",
            "disagreement_points": [{"topic": "risk"}, {"topic": "cost"}],
        }
        await emit_decision_from_synthesis("run-1", brief, 0.75)
        mock_publish.assert_called_once()
        call_payload = mock_publish.call_args[0][2]
        assert call_payload["decision_text"] == "Launch the product"
        assert call_payload["confidence"] == 0.75
        assert call_payload["dissent_count"] == 2

    @pytest.mark.asyncio
    async def test_emit_from_synthesis_fallback_to_recommendation(self, mock_publish):
        brief = {
            "decision_summary": "",
            "recommendation": "No-Go",
            "disagreement_points": [],
        }
        await emit_decision_from_synthesis("run-1", brief, 0.3)
        call_payload = mock_publish.call_args[0][2]
        assert call_payload["decision_text"] == "No-Go"
        assert call_payload["dissent_count"] == 0

    @pytest.mark.asyncio
    async def test_emit_from_synthesis_no_text_skips(self, mock_publish):
        brief = {"decision_summary": "", "recommendation": ""}
        await emit_decision_from_synthesis("run-1", brief, 0.5)
        mock_publish.assert_not_called()


# ── process_round_theater_events (integration hook) ──────────────────

class TestProcessRoundTheaterEvents:
    @pytest.mark.asyncio
    async def test_first_round_emits_claims_and_alliances(self, mock_publish):
        args = [
            _make_arg(0, "賛成", "My strong argument"),
            _make_arg(1, "賛成", "I agree with this"),
        ]
        await process_round_theater_events("run-1", args, prev_round=None)
        # Should emit: 2 claim_made + 1 alliance_formed = 3 calls
        event_types = [call[0][1] for call in mock_publish.call_args_list]
        assert event_types.count("claim_made") == 2
        assert event_types.count("alliance_formed") == 1
        assert "stance_shifted" not in event_types  # no prev round

    @pytest.mark.asyncio
    async def test_subsequent_round_emits_stance_shifts(self, mock_publish):
        prev = [_make_arg(0, "反対", "old arg")]
        curr = [_make_arg(0, "賛成", "new arg", belief_update="changed mind")]
        await process_round_theater_events("run-1", curr, prev_round=prev)
        event_types = [call[0][1] for call in mock_publish.call_args_list]
        assert "claim_made" in event_types
        assert "stance_shifted" in event_types
