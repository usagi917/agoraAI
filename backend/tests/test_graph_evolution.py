"""社会グラフ進化テスト"""

from src.app.services.society.graph_evolution import _compute_interaction_strength


class TestComputeInteractionStrength:
    def test_co_occurrence(self):
        rounds = [
            [
                {"participant_index": 0, "position": "賛成"},
                {"participant_index": 1, "position": "反対"},
            ],
            [
                {"participant_index": 0, "position": "条件付き賛成"},
                {"participant_index": 1, "position": "条件付き賛成"},
            ],
        ]
        delta = _compute_interaction_strength(rounds, "a", "b", 0, 1)
        assert delta > 0
        # 2/2 co-occurrence + 1/2 agreement
        assert delta <= 0.15

    def test_no_co_occurrence(self):
        rounds = [
            [{"participant_index": 0, "position": "賛成"}],
            [{"participant_index": 1, "position": "反対"}],
        ]
        delta = _compute_interaction_strength(rounds, "a", "b", 0, 1)
        assert delta == 0.0

    def test_empty_rounds(self):
        delta = _compute_interaction_strength([], "a", "b", 0, 1)
        assert delta == 0.0

    def test_full_agreement(self):
        rounds = [
            [
                {"participant_index": 0, "position": "賛成"},
                {"participant_index": 1, "position": "賛成"},
            ],
        ]
        delta = _compute_interaction_strength(rounds, "a", "b", 0, 1)
        assert delta > 0
