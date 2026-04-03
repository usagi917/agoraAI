"""Scenario Comparison のテスト (Stream E)"""

from src.app.services.scenario_comparison import (
    build_delta_brief,
    build_coalition_map,
    extract_opinion_shifts_top5,
)


# ---------------------------------------------------------------------------
# Mock decision briefs
# ---------------------------------------------------------------------------

BASELINE_BRIEF = {
    "recommendation": "条件付きGo",
    "decision_summary": "住宅補助金は一部支持を得るが懸念あり",
    "agreement_score": 0.56,
    "key_reasons": [
        {"reason": "低所得層の住環境改善", "confidence": 0.8},
    ],
    "guardrails": [
        {"condition": "財源確保", "status": "未確認"},
    ],
    "critical_unknowns": [
        {"question": "長期的な財政影響"},
    ],
}

INTERVENTION_BRIEF = {
    "recommendation": "Go",
    "decision_summary": "住宅補助金は広い支持を得た",
    "agreement_score": 0.65,
    "key_reasons": [
        {"reason": "低所得層の住環境改善", "confidence": 0.9},
        {"reason": "地域経済活性化", "confidence": 0.7},
    ],
    "guardrails": [
        {"condition": "財源確保", "status": "確認済"},
    ],
    "critical_unknowns": [],
}


# ---------------------------------------------------------------------------
# Tests: build_delta_brief
# ---------------------------------------------------------------------------


class TestBuildDeltaBrief:
    def test_support_change(self):
        """agreement_score の差分が正しく計算される"""
        delta = build_delta_brief(BASELINE_BRIEF, INTERVENTION_BRIEF)
        assert delta["support_change"] == round(0.65 - 0.56, 4)
        assert delta["support_change"] > 0

    def test_recommendation_change(self):
        """推奨が変化したことを検出する"""
        delta = build_delta_brief(BASELINE_BRIEF, INTERVENTION_BRIEF)
        assert delta["recommendation_change"] is not None
        assert delta["recommendation_change"]["before"] == "条件付きGo"
        assert delta["recommendation_change"]["after"] == "Go"

    def test_new_concerns(self):
        """介入側にのみ存在する懸念を検出する"""
        # baseline has "長期的な財政影響", intervention has none
        # So new_concerns should be empty (no concerns appeared only in intervention)
        delta = build_delta_brief(BASELINE_BRIEF, INTERVENTION_BRIEF)
        assert delta["new_concerns"] == []

    def test_resolved_concerns(self):
        """ベースラインにのみ存在する懸念 = 解消された懸念"""
        delta = build_delta_brief(BASELINE_BRIEF, INTERVENTION_BRIEF)
        assert "長期的な財政影響" in delta["resolved_concerns"]

    def test_new_concerns_present(self):
        """介入で新たに出現した懸念を検出する"""
        intervention = {
            **INTERVENTION_BRIEF,
            "critical_unknowns": [
                {"question": "環境負荷の増大"},
            ],
        }
        delta = build_delta_brief(BASELINE_BRIEF, intervention)
        assert "環境負荷の増大" in delta["new_concerns"]

    def test_guardrail_changes(self):
        """ガードレールのステータス変化を検出する"""
        delta = build_delta_brief(BASELINE_BRIEF, INTERVENTION_BRIEF)
        assert len(delta["guardrail_changes"]) == 1
        change = delta["guardrail_changes"][0]
        assert change["condition"] == "財源確保"
        assert change["before"] == "未確認"
        assert change["after"] == "確認済"

    def test_key_differences_populated(self):
        """key_differences が最大 3 件生成される"""
        delta = build_delta_brief(BASELINE_BRIEF, INTERVENTION_BRIEF)
        assert 1 <= len(delta["key_differences"]) <= 3
        # Should mention recommendation change and support score change
        diffs_text = " ".join(delta["key_differences"])
        assert "Go" in diffs_text or "支持" in diffs_text

    def test_identical_briefs_zero_changes(self):
        """同一の brief 同士では変化ゼロ"""
        delta = build_delta_brief(BASELINE_BRIEF, BASELINE_BRIEF)
        assert delta["support_change"] == 0.0
        assert delta["recommendation_change"] is None
        assert delta["new_concerns"] == []
        assert delta["resolved_concerns"] == []
        assert delta["guardrail_changes"] == []
        assert delta["key_differences"] == []
        assert delta["coalition_shifts"] == []


# ---------------------------------------------------------------------------
# Tests: build_coalition_map
# ---------------------------------------------------------------------------

MOCK_AGENTS = [
    {"age_bracket": "18-29", "region": "東京", "occupation": "学生", "primary_value": "教育", "stance": 0.8},
    {"age_bracket": "18-29", "region": "東京", "occupation": "学生", "primary_value": "教育", "stance": 0.6},
    {"age_bracket": "18-29", "region": "大阪", "occupation": "学生", "primary_value": "経済", "stance": 0.3},
    {"age_bracket": "30-49", "region": "東京", "occupation": "会社員", "primary_value": "経済", "stance": 0.9},
    {"age_bracket": "30-49", "region": "大阪", "occupation": "会社員", "primary_value": "経済", "stance": 0.4},
    {"age_bracket": "50+", "region": "大阪", "occupation": "自営業", "primary_value": "安全", "stance": 0.2},
]


class TestBuildCoalitionMap:
    def test_correct_group_breakdown(self):
        """既知のデモグラフィックから正しいグループ分けが行われる"""
        cmap = build_coalition_map(MOCK_AGENTS)

        # Check all 4 dimensions exist
        assert "by_age" in cmap
        assert "by_region" in cmap
        assert "by_occupation" in cmap
        assert "by_value" in cmap

    def test_age_groups_correct(self):
        """年齢グループの集計が正しい"""
        cmap = build_coalition_map(MOCK_AGENTS)
        age_groups = {g["group"]: g for g in cmap["by_age"]}

        # 18-29: 3 agents, 2 support (0.8, 0.6), 1 oppose (0.3) -> support=2/3
        assert age_groups["18-29"]["count"] == 3
        assert abs(age_groups["18-29"]["support"] - 2 / 3) < 0.01

        # 30-49: 2 agents, 1 support (0.9), 1 oppose (0.4) -> support=1/2
        assert age_groups["30-49"]["count"] == 2
        assert age_groups["30-49"]["support"] == 0.5

        # 50+: 1 agent, 0 support (0.2) -> support=0.0
        assert age_groups["50+"]["count"] == 1
        assert age_groups["50+"]["support"] == 0.0

    def test_region_groups(self):
        """地域グループの集計が正しい"""
        cmap = build_coalition_map(MOCK_AGENTS)
        region_groups = {g["group"]: g for g in cmap["by_region"]}

        # 東京: 3 agents (0.8, 0.6, 0.9) -> 3 support / 3 total
        assert region_groups["東京"]["count"] == 3
        assert region_groups["東京"]["support"] == 1.0

        # 大阪: 3 agents (0.3, 0.4, 0.2) -> 0 support / 3 total
        assert region_groups["大阪"]["count"] == 3
        assert region_groups["大阪"]["support"] == 0.0

    def test_support_oppose_sum_to_one(self):
        """各グループの support + oppose が 1.0 になる"""
        cmap = build_coalition_map(MOCK_AGENTS)
        for dimension in ("by_age", "by_region", "by_occupation", "by_value"):
            for group in cmap[dimension]:
                total = group["support"] + group["oppose"]
                assert abs(total - 1.0) < 0.001, f"{dimension}/{group['group']}: {total}"

    def test_empty_agents(self):
        """空のエージェントリストではすべて空配列"""
        cmap = build_coalition_map([])
        assert cmap["by_age"] == []
        assert cmap["by_region"] == []
        assert cmap["by_occupation"] == []
        assert cmap["by_value"] == []

    def test_missing_demographics(self):
        """デモグラフィック情報がないエージェントは '不明' グループに入る"""
        agents = [
            {"stance": 0.7},  # No demographic info
            {"stance": 0.3},
        ]
        cmap = build_coalition_map(agents)
        for dimension in ("by_age", "by_region", "by_occupation", "by_value"):
            assert len(cmap[dimension]) == 1
            assert cmap[dimension][0]["group"] == "不明"
            assert cmap[dimension][0]["count"] == 2


# ---------------------------------------------------------------------------
# Tests: extract_opinion_shifts_top5
# ---------------------------------------------------------------------------


class TestExtractOpinionShiftsTop5:
    def test_top5_by_magnitude(self):
        """shift magnitude の大きい順に上位 5 件が返る"""
        events = [
            {"agent_id": f"a{i}", "agent_name": f"Agent {i}", "before_state": {"stance": 0.5}, "after_state": {"stance": 0.5 + i * 0.05}, "reasoning": ""}
            for i in range(10)
        ]
        top5 = extract_opinion_shifts_top5(events)
        assert len(top5) == 5
        # Largest shift first
        assert top5[0]["shift_magnitude"] >= top5[1]["shift_magnitude"]
        assert top5[0]["agent_id"] == "a9"  # biggest shift: |0.5 - (0.5+0.45)| = 0.45

    def test_returns_max_5(self):
        """6 件以上あっても 5 件まで"""
        events = [
            {"agent_id": f"a{i}", "agent_name": f"Agent {i}", "before_state": {"stance": 0.0}, "after_state": {"stance": float(i)}, "reasoning": ""}
            for i in range(8)
        ]
        top5 = extract_opinion_shifts_top5(events)
        assert len(top5) == 5

    def test_empty_events(self):
        """空のイベントリストでは空を返す"""
        top5 = extract_opinion_shifts_top5([])
        assert top5 == []

    def test_single_event(self):
        """1 件のみのイベント"""
        events = [
            {"agent_id": "a1", "agent_name": "Alice", "before_state": {"stance": 0.2}, "after_state": {"stance": 0.9}, "reasoning": "Evidence changed"},
        ]
        top5 = extract_opinion_shifts_top5(events)
        assert len(top5) == 1
        assert top5[0]["agent_name"] == "Alice"
        assert top5[0]["shift_magnitude"] == 0.7

    def test_shift_from_multiple_keys(self):
        """stance 以外のキー (support) でも magnitude が計算される"""
        events = [
            {"agent_id": "a1", "agent_name": "Bob", "before_state": {"support": 0.1}, "after_state": {"support": 0.8}, "reasoning": ""},
        ]
        top5 = extract_opinion_shifts_top5(events)
        assert len(top5) == 1
        assert abs(top5[0]["shift_magnitude"] - 0.7) < 0.001

    def test_fallback_to_key_count(self):
        """数値キーがない場合、変化したキー数を magnitude として使う"""
        events = [
            {"agent_id": "a1", "agent_name": "Carol", "before_state": {"opinion": "agree"}, "after_state": {"opinion": "disagree", "reason": "new info"}, "reasoning": ""},
        ]
        top5 = extract_opinion_shifts_top5(events)
        assert len(top5) == 1
        # 2 keys changed: opinion changed, reason is new
        assert top5[0]["shift_magnitude"] == 2.0
