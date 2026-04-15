"""P6-3: フィルターバブル幅パラメータ テスト

opinion_dynamics.py の compute_filter_bubble_thresholds() をテスト。
エージェントの情報源多様性に基づいて confidence_threshold を調整し、
フィルターバブルの効果をシミュレートする。
"""

import numpy as np
import pytest


class TestFilterBubbleThresholds:
    """フィルターバブル幅パラメータのテスト."""

    def test_diverse_sources_wider_threshold(self):
        """多様な情報源を持つエージェントは閾値が広い."""
        from src.app.services.society.opinion_dynamics import compute_filter_bubble_thresholds

        agents = [
            {
                "id": "a1",
                "information_source": "テレビニュース",
                "big_five": {"O": 0.5, "C": 0.5},
            },
            {
                "id": "a2",
                "information_source": "SNS(Twitter/X)",
                "big_five": {"O": 0.5, "C": 0.5},
            },
        ]

        thresholds = compute_filter_bubble_thresholds(
            agents,
            base_threshold=0.3,
            bubble_width=0.5,
        )

        assert len(thresholds) == 2
        assert all(t > 0 for t in thresholds)

    def test_bubble_width_zero_returns_base(self):
        """bubble_width=0 のとき全員がベース閾値."""
        from src.app.services.society.opinion_dynamics import compute_filter_bubble_thresholds

        agents = [
            {"id": "a1", "information_source": "SNS(Twitter/X)", "big_five": {"O": 0.5, "C": 0.5}},
            {"id": "a2", "information_source": "新聞", "big_five": {"O": 0.5, "C": 0.5}},
        ]

        thresholds = compute_filter_bubble_thresholds(
            agents, base_threshold=0.3, bubble_width=0.0,
        )

        np.testing.assert_array_almost_equal(thresholds, [0.3, 0.3])

    def test_bubble_width_one_max_effect(self):
        """bubble_width=1.0 で最大のフィルターバブル効果."""
        from src.app.services.society.opinion_dynamics import compute_filter_bubble_thresholds

        agents = [
            {"id": "a1", "information_source": "SNS(Twitter/X)", "big_five": {"O": 0.2, "C": 0.5}},
            {"id": "a2", "information_source": "新聞", "big_five": {"O": 0.8, "C": 0.5}},
        ]

        t_max = compute_filter_bubble_thresholds(agents, base_threshold=0.3, bubble_width=1.0)
        t_mid = compute_filter_bubble_thresholds(agents, base_threshold=0.3, bubble_width=0.5)

        # bubble_width が大きいほど、情報源による閾値差が拡大する
        spread_max = abs(float(t_max[0]) - float(t_max[1]))
        spread_mid = abs(float(t_mid[0]) - float(t_mid[1]))
        assert spread_max >= spread_mid

    def test_sns_users_have_narrower_threshold(self):
        """SNS 主体の情報源はフィルターバブルにより閾値が狭い."""
        from src.app.services.society.opinion_dynamics import compute_filter_bubble_thresholds

        agents = [
            {"id": "a1", "information_source": "SNS(Twitter/X)", "big_five": {"O": 0.5, "C": 0.5}},
            {"id": "a2", "information_source": "新聞", "big_five": {"O": 0.5, "C": 0.5}},
        ]

        thresholds = compute_filter_bubble_thresholds(
            agents, base_threshold=0.3, bubble_width=0.8,
        )

        # SNS ユーザーは新聞読者よりも閾値が狭い（バブル効果）
        assert thresholds[0] < thresholds[1]

    def test_engine_accepts_filter_bubble_thresholds(self):
        """OpinionDynamicsEngine がフィルターバブル閾値で動作すること."""
        from src.app.services.society.opinion_dynamics import (
            OpinionDynamicsEngine,
            compute_filter_bubble_thresholds,
        )

        agents_data = [
            {"id": "a1", "information_source": "SNS(Twitter/X)", "big_five": {"O": 0.3, "C": 0.5}},
            {"id": "a2", "information_source": "新聞", "big_five": {"O": 0.7, "C": 0.5}},
        ]

        thresholds = compute_filter_bubble_thresholds(
            agents_data, base_threshold=0.3, bubble_width=0.5,
        )

        engine_agents = [
            {"id": "a1", "opinion_vector": [0.4, 0.6], "stubbornness": 0.5},
            {"id": "a2", "opinion_vector": [0.6, 0.4], "stubbornness": 0.5},
        ]
        edges = [
            {"agent_id": "a1", "target_id": "a2", "strength": 0.8},
            {"agent_id": "a2", "target_id": "a1", "strength": 0.8},
        ]

        engine = OpinionDynamicsEngine(engine_agents, edges, confidence_threshold=thresholds)
        result = engine.propagation_step(1)
        assert result.timestep == 1

    def test_minimum_threshold_enforced(self):
        """閾値の最小値 (0.05) が保証されること."""
        from src.app.services.society.opinion_dynamics import compute_filter_bubble_thresholds

        agents = [
            {"id": "a1", "information_source": "SNS(Twitter/X)", "big_five": {"O": 0.0, "C": 1.0}},
        ]

        thresholds = compute_filter_bubble_thresholds(
            agents, base_threshold=0.05, bubble_width=1.0,
        )

        assert thresholds[0] >= 0.05

    def test_returns_ndarray(self):
        """numpy ndarray を返すこと."""
        from src.app.services.society.opinion_dynamics import compute_filter_bubble_thresholds

        agents = [
            {"id": "a1", "information_source": "テレビニュース", "big_five": {"O": 0.5, "C": 0.5}},
        ]

        thresholds = compute_filter_bubble_thresholds(
            agents, base_threshold=0.3, bubble_width=0.5,
        )

        assert isinstance(thresholds, np.ndarray)
        assert thresholds.dtype == np.float64
