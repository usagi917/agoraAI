"""P3-4: フォロワーダイナミクスのテスト"""

import pytest


class TestFollowerDynamics:
    """follower_dynamics.py のテスト."""

    def test_compute_follower_opinion(self):
        """隣接リーダーの意見加重平均が返ること."""
        from src.app.services.society.follower_dynamics import compute_follower_opinion

        leader_opinions = [
            {"agent_id": "l1", "stance": "賛成", "confidence": 0.9, "weight": 0.6},
            {"agent_id": "l2", "stance": "反対", "confidence": 0.7, "weight": 0.4},
        ]

        result = compute_follower_opinion(leader_opinions, follower_id="f1")

        assert "stance" in result
        assert "confidence" in result
        assert "reason" in result
        assert "concern" in result
        assert result["agent_id"] == "f1"

    def test_majority_stance(self):
        """加重多数決でスタンスが決まること."""
        from src.app.services.society.follower_dynamics import compute_follower_opinion

        leader_opinions = [
            {"agent_id": "l1", "stance": "賛成", "confidence": 0.8, "weight": 0.7},
            {"agent_id": "l2", "stance": "賛成", "confidence": 0.6, "weight": 0.2},
            {"agent_id": "l3", "stance": "反対", "confidence": 0.9, "weight": 0.1},
        ]

        result = compute_follower_opinion(leader_opinions, follower_id="f1")
        assert result["stance"] == "賛成"

    def test_confidence_is_weighted_average(self):
        """confidence が加重平均であること."""
        from src.app.services.society.follower_dynamics import compute_follower_opinion

        leader_opinions = [
            {"agent_id": "l1", "stance": "賛成", "confidence": 0.8, "weight": 0.5},
            {"agent_id": "l2", "stance": "賛成", "confidence": 0.4, "weight": 0.5},
        ]

        result = compute_follower_opinion(leader_opinions, follower_id="f1")
        assert abs(result["confidence"] - 0.6) < 0.01  # (0.8*0.5 + 0.4*0.5) / 1.0

    def test_empty_leaders(self):
        """リーダーが空の場合はデフォルトの中立意見."""
        from src.app.services.society.follower_dynamics import compute_follower_opinion

        result = compute_follower_opinion([], follower_id="f1")
        assert result["stance"] == "中立"
        assert result["confidence"] == 0.5

    def test_follower_response_protocol(self):
        """FollowerResponse プロトコルに必要なフィールドがすべてあること."""
        from src.app.services.society.follower_dynamics import compute_follower_opinion

        leader_opinions = [
            {"agent_id": "l1", "stance": "賛成", "confidence": 0.8, "weight": 0.5},
        ]

        result = compute_follower_opinion(leader_opinions, follower_id="f1")

        required_keys = {"stance", "confidence", "reason", "concern", "agent_id"}
        assert required_keys.issubset(result.keys())
