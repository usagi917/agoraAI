"""熟議品質評価モジュールのテスト (Discourse Quality Index に基づく)

Steenbergen et al. (2003) の DQI フレームワークを参照。
LLM 非依存のヒューリスティック版 compute_dqi を対象とする。
"""

import pytest

from src.app.services.society.deliberation_quality import (
    compute_argument_quality,
    compute_dqi,
    measure_opinion_change,
)

# ---------------------------------------------------------------------------
# 共通テストデータ
# ---------------------------------------------------------------------------

# 会議ラウンドデータ（Round 1, 2, 3）
MEETING_ROUNDS = [
    [  # Round 1: 初期主張
        {
            "participant": "田中（会社員・35歳）",
            "position": "賛成",
            "argument": "うちの会社ではこの政策のおかげで...",
            "evidence": "売上が15%増加",
            "addressed_to": "",
            "belief_update": "",
            "concerns": ["コスト"],
            "questions_to_others": ["反対派の根拠は？"],
        },
        {
            "participant": "鈴木（農業・62歳）",
            "position": "反対",
            "argument": "地方の農家にとってはデメリットしかない...",
            "evidence": "隣町で同様の政策が失敗",
            "addressed_to": "",
            "belief_update": "",
            "concerns": ["地方切り捨て"],
            "questions_to_others": [],
        },
        {
            "participant": "佐藤（主婦・45歳）",
            "position": "条件付き賛成",
            "argument": "子育て世帯への配慮があれば...",
            "evidence": "",
            "addressed_to": "",
            "belief_update": "",
            "concerns": ["教育費"],
            "questions_to_others": [],
        },
    ],
    [  # Round 2: 相互質疑
        {
            "participant": "田中（会社員・35歳）",
            "position": "賛成",
            "argument": "鈴木さんの懸念はわかるが、データを見ると...",
            "evidence": "農水省の報告書",
            "addressed_to": "鈴木",
            "belief_update": "",
            "concerns": [],
            "questions_to_others": [],
        },
        {
            "participant": "鈴木（農業・62歳）",
            "position": "条件付き反対",
            "argument": "田中さんの指摘は一理ある。しかし...",
            "evidence": "",
            "addressed_to": "田中",
            "belief_update": "都市部のメリットは認める",
            "concerns": [],
            "questions_to_others": [],
        },
        {
            "participant": "佐藤（主婦・45歳）",
            "position": "条件付き賛成",
            "argument": "両者の意見を聞いて...",
            "evidence": "",
            "addressed_to": "田中, 鈴木",
            "belief_update": "",
            "concerns": [],
            "questions_to_others": [],
        },
    ],
    [  # Round 3: 最終立場
        {
            "participant": "田中（会社員・35歳）",
            "position": "賛成",
            "argument": "総合的に判断して推進すべき",
            "evidence": "",
            "addressed_to": "",
            "belief_update": "",
            "concerns": [],
            "questions_to_others": [],
        },
        {
            "participant": "鈴木（農業・62歳）",
            "position": "条件付き賛成",
            "argument": "地方への補助がセットなら...",
            "evidence": "",
            "addressed_to": "",
            "belief_update": "田中さんのデータと佐藤さんの提案に説得された",
            "concerns": [],
            "questions_to_others": [],
        },
        {
            "participant": "佐藤（主婦・45歳）",
            "position": "賛成",
            "argument": "議論を通じて全体像が見えた",
            "evidence": "",
            "addressed_to": "",
            "belief_update": "当初の条件は議論で解消された",
            "concerns": [],
            "questions_to_others": [],
        },
    ],
]

# 変化なしデータ（全員が Round 1 と同じ position を Round 3 でも持つ）
NO_CHANGE_ROUNDS = [
    [  # Round 1
        {"participant": "A", "position": "賛成", "argument": "...", "evidence": "", "addressed_to": "", "belief_update": "", "concerns": [], "questions_to_others": []},
        {"participant": "B", "position": "反対", "argument": "...", "evidence": "", "addressed_to": "", "belief_update": "", "concerns": [], "questions_to_others": []},
    ],
    [  # Round 2 (intermediate — positions unchanged)
        {"participant": "A", "position": "賛成", "argument": "...", "evidence": "", "addressed_to": "", "belief_update": "", "concerns": [], "questions_to_others": []},
        {"participant": "B", "position": "反対", "argument": "...", "evidence": "", "addressed_to": "", "belief_update": "", "concerns": [], "questions_to_others": []},
    ],
    [  # Round 3 (same as Round 1)
        {"participant": "A", "position": "賛成", "argument": "...", "evidence": "", "addressed_to": "", "belief_update": "", "concerns": [], "questions_to_others": []},
        {"participant": "B", "position": "反対", "argument": "...", "evidence": "", "addressed_to": "", "belief_update": "", "concerns": [], "questions_to_others": []},
    ],
]


# ---------------------------------------------------------------------------
# measure_opinion_change のテスト
# ---------------------------------------------------------------------------


class TestMeasureOpinionChange:
    def test_opinion_change_detects_shift(self):
        """鈴木が「反対」→「条件付き賛成」に変化 → change_rate > 0"""
        result = measure_opinion_change(MEETING_ROUNDS)

        assert "change_rate" in result
        assert result["change_rate"] > 0.0

    def test_opinion_change_shift_includes_suzuki(self):
        """changes リストに鈴木のシフトが含まれる"""
        result = measure_opinion_change(MEETING_ROUNDS)

        participants_changed = [c["participant"] for c in result["changes"]]
        assert any("鈴木" in p for p in participants_changed)

    def test_opinion_change_shift_records_from_to(self):
        """changes の各エントリに from, to が記録されている"""
        result = measure_opinion_change(MEETING_ROUNDS)

        for change in result["changes"]:
            assert "participant" in change
            assert "from" in change
            assert "to" in change
            # from と to は異なる
            assert change["from"] != change["to"]

    def test_opinion_change_no_shift(self):
        """Round 1 と Round 3 が全員同じ position → change_rate = 0"""
        result = measure_opinion_change(NO_CHANGE_ROUNDS)

        assert result["change_rate"] == 0.0
        assert result["changes"] == []

    def test_opinion_change_comparison_with_fishkin(self):
        """返り値に fishkin_comparison キーがあり、典型値との比較コメントを含む"""
        result = measure_opinion_change(MEETING_ROUNDS)

        assert "fishkin_comparison" in result
        assert isinstance(result["fishkin_comparison"], str)
        assert len(result["fishkin_comparison"]) > 0

    def test_opinion_change_change_rate_range(self):
        """change_rate は 0.0–1.0 の範囲内"""
        result = measure_opinion_change(MEETING_ROUNDS)

        assert 0.0 <= result["change_rate"] <= 1.0

    def test_opinion_change_single_round_returns_zero(self):
        """ラウンドが1つしかない場合 → 変化率 0（比較不可）"""
        single_round = [MEETING_ROUNDS[0]]
        result = measure_opinion_change(single_round)

        assert result["change_rate"] == 0.0
        assert result["changes"] == []

    def test_opinion_change_empty_rounds(self):
        """空リストを渡した場合 → change_rate = 0"""
        result = measure_opinion_change([])

        assert result["change_rate"] == 0.0
        assert result["changes"] == []


# ---------------------------------------------------------------------------
# compute_argument_quality のテスト
# ---------------------------------------------------------------------------


class TestComputeArgumentQuality:
    def test_argument_quality_scores_evidence(self):
        """証拠を含む argument → evidence_score > 0"""
        argument = "この政策はうちの会社で実際に効果があった。売上が15%増加した。"
        evidence = "売上が15%増加"
        result = compute_argument_quality(argument, evidence)

        assert "evidence_score" in result
        assert result["evidence_score"] > 0.0

    def test_argument_quality_scores_no_evidence(self):
        """証拠なし・短い argument → evidence_score = 0"""
        argument = "なんとなく良いと思う。"
        evidence = ""
        result = compute_argument_quality(argument, evidence)

        assert result["evidence_score"] == 0.0

    def test_argument_quality_has_required_keys(self):
        """返り値に必要なキーが全て含まれる"""
        result = compute_argument_quality("テスト", "")

        required_keys = {
            "evidence_score",
            "counterargument_score",
            "conditional_reasoning_score",
            "personal_experience_score",
            "overall",
        }
        assert required_keys.issubset(result.keys())

    def test_argument_quality_scores_in_range(self):
        """全スコアが 0.0–1.0 の範囲内"""
        result = compute_argument_quality(
            "鈴木さんの懸念はわかるが、データを見ると改善が見込める。もし問題があれば補助金で対応できる。",
            "農水省の報告書",
        )
        for key, value in result.items():
            assert 0.0 <= value <= 1.0, f"{key} = {value} is out of range"

    def test_argument_quality_counterargument_detection(self):
        """反論への言及（「わかる」「一理ある」「理解」）→ counterargument_score > 0"""
        argument = "田中さんの指摘は一理あるが、地方への配慮が必要だ。"
        result = compute_argument_quality(argument, "")

        assert result["counterargument_score"] > 0.0

    def test_argument_quality_conditional_reasoning(self):
        """条件付き表現（「もし」「〜なら」「〜であれば」）→ conditional_reasoning_score > 0"""
        argument = "もし補助金が出るなら賛成できる。地方への配慮があれば問題ない。"
        result = compute_argument_quality(argument, "")

        assert result["conditional_reasoning_score"] > 0.0

    def test_argument_quality_personal_experience(self):
        """個人体験（「うちの」「私の」「自分の」）→ personal_experience_score > 0"""
        argument = "うちの地域では以前同じ政策が失敗した経験がある。"
        result = compute_argument_quality(argument, "")

        assert result["personal_experience_score"] > 0.0

    def test_argument_quality_empty_argument(self):
        """空 argument → overall = 0"""
        result = compute_argument_quality("", "")

        assert result["overall"] == 0.0

    def test_argument_quality_overall_reflects_components(self):
        """overall は各スコアの平均値"""
        result = compute_argument_quality(
            "鈴木さんの懸念はわかる。もし補助があれば賛成できる。",
            "農水省のデータ",
        )
        components = [
            result["evidence_score"],
            result["counterargument_score"],
            result["conditional_reasoning_score"],
            result["personal_experience_score"],
        ]
        expected_overall = sum(components) / len(components)
        assert abs(result["overall"] - expected_overall) < 1e-9


# ---------------------------------------------------------------------------
# compute_dqi のテスト
# ---------------------------------------------------------------------------


class TestComputeDqi:
    def test_dqi_returns_five_dimensions(self):
        """返り値の dimensions キーに 5 次元が含まれる"""
        result = compute_dqi(MEETING_ROUNDS)

        assert "dimensions" in result
        dimensions = result["dimensions"]
        expected_dims = {
            "justification_level",
            "justification_content",
            "respect_groups",
            "respect_counterarguments",
            "constructive_politics",
        }
        assert expected_dims.issubset(dimensions.keys())

    def test_dqi_scores_in_valid_range(self):
        """全スコアが 0.0–1.0 の範囲内"""
        result = compute_dqi(MEETING_ROUNDS)

        for dim, score in result["dimensions"].items():
            assert 0.0 <= score <= 1.0, f"{dim} = {score} is out of [0, 1]"

        assert "overall_dqi" in result
        assert 0.0 <= result["overall_dqi"] <= 1.0

    def test_dqi_justification_level_counts_evidence(self):
        """evidence が空でない発言の割合が justification_level に反映される"""
        result = compute_dqi(MEETING_ROUNDS)

        # Round 1 で 2/3 が evidence あり, Round 2 で 2/3, Round 3 で 0/3
        # 全体: 4/9 ≈ 0.44 — 0 より大きいことを確認
        assert result["dimensions"]["justification_level"] > 0.0

    def test_dqi_respect_counterarguments_counts_addressed_to(self):
        """addressed_to が空でない発言の割合が respect_counterarguments に反映される"""
        result = compute_dqi(MEETING_ROUNDS)

        # Round 2 で 3/3 が addressed_to あり → > 0
        assert result["dimensions"]["respect_counterarguments"] > 0.0

    def test_dqi_respect_groups_counts_empathy_expressions(self):
        """「わかる」「一理ある」「理解」を含む発言の割合が respect_groups に反映される"""
        result = compute_dqi(MEETING_ROUNDS)

        # Round 2 の田中「わかる」と鈴木「一理ある」→ > 0
        assert result["dimensions"]["respect_groups"] > 0.0

    def test_dqi_overall_is_mean_of_dimensions(self):
        """overall_dqi は 5 次元スコアの平均 (丸め誤差許容: 1e-4)"""
        result = compute_dqi(MEETING_ROUNDS)

        dims = result["dimensions"]
        expected = sum(dims.values()) / len(dims)
        # 各次元は round(x, 4) 済みのため overall との差は最大 5 * 0.00005 / 5 = 0.00005
        assert abs(result["overall_dqi"] - expected) < 1e-4

    def test_dqi_empty_rounds(self):
        """空ラウンドでも KeyError が発生せずスコアが返る"""
        result = compute_dqi([])

        assert "dimensions" in result
        assert "overall_dqi" in result
        # 全スコアが 0
        for score in result["dimensions"].values():
            assert score == 0.0
        assert result["overall_dqi"] == 0.0

    def test_dqi_single_round(self):
        """ラウンドが 1 つでも正常に動作する"""
        result = compute_dqi([MEETING_ROUNDS[0]])

        assert "dimensions" in result
        assert "overall_dqi" in result
        for score in result["dimensions"].values():
            assert 0.0 <= score <= 1.0
