"""Tests for Stigmergy Service: pheromone-based topic importance tracking.

Verifies:
- Topic deposit increases intensity
- Evaporation decreases intensity over time
- Salient topics are ranked by intensity
- Multiple agents depositing on same topic accumulates
"""

import pytest

from src.app.services.society.stigmergy_service import StigmergyBoard


class TestDeposit:
    """Agents depositing on a topic should increase its intensity."""

    def test_single_deposit(self):
        board = StigmergyBoard()
        board.deposit("agent_0", "財源問題", intensity=1.0)

        topics = board.get_salient_topics(top_k=5)
        assert len(topics) == 1
        assert topics[0].topic == "財源問題"
        assert topics[0].intensity == pytest.approx(1.0)
        assert "agent_0" in topics[0].contributors

    def test_multiple_deposits_same_topic(self):
        board = StigmergyBoard()
        board.deposit("agent_0", "財源問題", intensity=1.0)
        board.deposit("agent_1", "財源問題", intensity=0.5)

        topics = board.get_salient_topics(top_k=5)
        assert len(topics) == 1
        assert topics[0].intensity == pytest.approx(1.5)
        assert len(topics[0].contributors) == 2

    def test_deposits_on_different_topics(self):
        board = StigmergyBoard()
        board.deposit("agent_0", "財源問題", intensity=2.0)
        board.deposit("agent_1", "教育格差", intensity=1.0)

        topics = board.get_salient_topics(top_k=5)
        assert len(topics) == 2
        assert topics[0].topic == "財源問題"  # higher intensity first
        assert topics[1].topic == "教育格差"


class TestEvaporation:
    """Topic intensity should decay over time."""

    def test_single_evaporation(self):
        board = StigmergyBoard()
        board.deposit("agent_0", "財源問題", intensity=1.0)
        board.evaporate(decay_rate=0.1)

        topics = board.get_salient_topics(top_k=5)
        assert topics[0].intensity == pytest.approx(0.9)

    def test_repeated_evaporation(self):
        board = StigmergyBoard()
        board.deposit("agent_0", "財源問題", intensity=1.0)
        for _ in range(10):
            board.evaporate(decay_rate=0.1)

        topics = board.get_salient_topics(top_k=5)
        # 1.0 * 0.9^10 ≈ 0.3487
        assert topics[0].intensity == pytest.approx(0.9**10, abs=0.01)

    def test_evaporation_preserves_ranking(self):
        board = StigmergyBoard()
        board.deposit("agent_0", "A", intensity=3.0)
        board.deposit("agent_1", "B", intensity=1.0)
        board.evaporate(decay_rate=0.5)

        topics = board.get_salient_topics(top_k=5)
        assert topics[0].topic == "A"
        assert topics[0].intensity > topics[1].intensity


class TestSalientTopics:
    """Top-K salient topics should be returned by intensity."""

    def test_top_k_limit(self):
        board = StigmergyBoard()
        for i in range(10):
            board.deposit("agent_0", f"topic_{i}", intensity=float(i))

        topics = board.get_salient_topics(top_k=3)
        assert len(topics) == 3
        assert topics[0].topic == "topic_9"  # highest

    def test_empty_board(self):
        board = StigmergyBoard()
        topics = board.get_salient_topics(top_k=5)
        assert topics == []


class TestSnapshot:
    """Board should be serializable to dict for persistence."""

    def test_snapshot_roundtrip(self):
        board = StigmergyBoard()
        board.deposit("agent_0", "A", intensity=2.0)
        board.deposit("agent_1", "B", intensity=1.0)

        snapshot = board.to_dict()
        restored = StigmergyBoard.from_dict(snapshot)

        assert len(restored.get_salient_topics(top_k=5)) == 2
        assert restored.get_salient_topics(top_k=1)[0].topic == "A"
