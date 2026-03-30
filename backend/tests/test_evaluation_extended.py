"""Phase 4-3 & 6-2: 拡張評価メトリクスのテスト (TDD フェーズ)

テスト対象:
- demographic_representativeness: 人口統計的代表性（カイ二乗適合度検定）
- response_quality_score: レスポンス品質スコア
- deliberation_depth: 熟議深度スコア
- detect_provider_bias: LLMプロバイダバイアス検出
"""

import pytest

from src.app.services.society.evaluation import (
    demographic_representativeness,
    deliberation_depth,
    response_quality_score,
    evaluate_society_simulation,
    detect_provider_bias,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(age: int) -> dict:
    return {"demographics": {"age": age, "gender": "male", "occupation": "会社員"}}


def _make_agents_uniform() -> list[dict]:
    """各年齢帯に10人ずつ（40人、一様分布）"""
    agents = []
    for age in [25, 35, 55, 75]:  # 18-29, 30-49, 50-69, 70+
        agents.extend([_make_agent(age)] * 10)
    return agents


def _make_agents_skewed() -> list[dict]:
    """全員18-29歳（40人、偏った分布）"""
    return [_make_agent(25)] * 40


TARGET_UNIFORM = {
    "age_bracket": {
        "18-29": 0.25,
        "30-49": 0.25,
        "50-69": 0.25,
        "70+":   0.25,
    }
}


# ---------------------------------------------------------------------------
# demographic_representativeness
# ---------------------------------------------------------------------------

class TestDemographicRepresentativeness:
    def test_demographic_representativeness_uniform(self):
        """一様分布のエージェント群とターゲットが完全一致 → p値 > 0.05（代表的）"""
        agents = _make_agents_uniform()
        p_value = demographic_representativeness(agents, TARGET_UNIFORM)
        assert isinstance(p_value, float)
        assert p_value > 0.05, f"Expected p > 0.05 (representative), got {p_value}"

    def test_demographic_representativeness_skewed(self):
        """全員同じ年齢帯 → p値 < 0.05（非代表的）"""
        agents = _make_agents_skewed()
        p_value = demographic_representativeness(agents, TARGET_UNIFORM)
        assert isinstance(p_value, float)
        assert p_value < 0.05, f"Expected p < 0.05 (unrepresentative), got {p_value}"

    def test_demographic_representativeness_returns_float_between_0_and_1(self):
        """返り値は 0.0〜1.0 の float"""
        agents = _make_agents_uniform()
        p_value = demographic_representativeness(agents, TARGET_UNIFORM)
        assert 0.0 <= p_value <= 1.0

    def test_demographic_representativeness_empty_agents(self):
        """エージェントが空 → 0.0 を返す（エラーにならない）"""
        p_value = demographic_representativeness([], TARGET_UNIFORM)
        assert p_value == 0.0

    def test_demographic_representativeness_empty_target(self):
        """ターゲットが空 → 0.0 を返す（エラーにならない）"""
        agents = _make_agents_uniform()
        p_value = demographic_representativeness(agents, {})
        assert p_value == 0.0

    def test_demographic_representativeness_nearly_uniform(self):
        """ほぼ一様な分布（わずかな偏差） → p > 0.05 を期待"""
        # 各帯 9, 10, 10, 11 人
        agents = (
            [_make_agent(25)] * 9
            + [_make_agent(35)] * 10
            + [_make_agent(55)] * 10
            + [_make_agent(75)] * 11
        )
        p_value = demographic_representativeness(agents, TARGET_UNIFORM)
        # わずかな偏差なので代表的と判断されるべき
        assert p_value > 0.05


# ---------------------------------------------------------------------------
# response_quality_score
# ---------------------------------------------------------------------------

def _make_good_response(text_len: int = 200) -> dict:
    """高品質レスポンス: reason が長く具体的な内容を含む"""
    reason = "具体的な根拠として、" + "経済的影響について詳しく説明します。" * (text_len // 20 + 1)
    return {"stance": "賛成", "confidence": 0.7, "reason": reason[:text_len]}


def _make_short_response() -> dict:
    """低品質レスポンス: reason が短い（< 100文字）"""
    return {"stance": "中立", "confidence": 0.5, "reason": "短い意見です。"}


def _make_default_response() -> dict:
    """デフォルトパターン（低品質）: 典型的なデフォルト回答"""
    return {"stance": "中立", "confidence": 0.5, "reason": "この問題については中立的な立場から判断します。"}


class TestResponseQualityScore:
    def test_response_quality_score_all_good(self):
        """全レスポンスが200文字以上で具体的 → スコア = 1.0"""
        responses = [_make_good_response(200) for _ in range(10)]
        score = response_quality_score(responses)
        assert score == 1.0, f"Expected 1.0, got {score}"

    def test_response_quality_score_mixed(self):
        """半分が短い回答 → スコア ≈ 0.5"""
        good = [_make_good_response(200) for _ in range(5)]
        short = [_make_short_response() for _ in range(5)]
        score = response_quality_score(good + short)
        assert 0.4 <= score <= 0.6, f"Expected ~0.5, got {score}"

    def test_response_quality_score_all_short(self):
        """全て短い回答 → スコア = 0.0"""
        responses = [_make_short_response() for _ in range(10)]
        score = response_quality_score(responses)
        assert score == 0.0, f"Expected 0.0, got {score}"

    def test_response_quality_score_empty(self):
        """空リスト → 0.0"""
        assert response_quality_score([]) == 0.0

    def test_response_quality_score_in_range(self):
        """返り値は 0.0〜1.0 の範囲"""
        responses = [_make_good_response(150), _make_short_response(), _make_good_response(220)]
        score = response_quality_score(responses)
        assert 0.0 <= score <= 1.0

    def test_response_quality_score_boundary_100_chars(self):
        """reason がちょうど 100文字 → 高品質判定"""
        # "詳細説明:" (5文字) + "あ" * 95 = 100文字
        reason = "詳細説明:" + "あ" * 95
        assert len(reason) == 100
        response = {"stance": "賛成", "confidence": 0.7, "reason": reason}
        score = response_quality_score([response])
        assert score == 1.0

    def test_response_quality_score_99_chars(self):
        """reason が 99文字 → 低品質判定"""
        reason = "a" * 99
        response = {"stance": "賛成", "confidence": 0.7, "reason": reason}
        score = response_quality_score([response])
        assert score == 0.0


# ---------------------------------------------------------------------------
# deliberation_depth
# ---------------------------------------------------------------------------

def _make_no_engagement_meeting() -> dict:
    """全員 addressed_to 空、belief_update 空 → 最低スコア期待"""
    return {
        "rounds": [
            [
                {"addressed_to": "", "belief_update": "", "argument": "短い意見"},
                {"addressed_to": "", "belief_update": "", "argument": "短い意見"},
            ],
            [
                {"addressed_to": "", "belief_update": "", "argument": "短い意見"},
                {"addressed_to": "", "belief_update": "", "argument": "短い意見"},
            ],
        ]
    }


def _make_full_engagement_meeting() -> dict:
    """全員が addressed_to を記入、belief_update あり → 高スコア期待"""
    long_arg = "この問題については複数の側面から考える必要があります。" * 5
    return {
        "rounds": [
            [
                {"addressed_to": "田中さん", "belief_update": "田中さんの意見を聞いて考えが変わりました", "argument": long_arg},
                {"addressed_to": "鈴木さん", "belief_update": "鈴木さんの指摘は鋭いと思います", "argument": long_arg},
            ],
            [
                {"addressed_to": "山田さん", "belief_update": "山田さんの観点は新しい視野を開きました", "argument": long_arg},
                {"addressed_to": "佐藤さん", "belief_update": "佐藤さんの経験談が参考になりました", "argument": long_arg},
            ],
        ]
    }


def _make_mixed_engagement_meeting() -> dict:
    """Round 1 はエンゲージメント低、Round 2 は高 → 中程度スコア"""
    return {
        "rounds": [
            [
                {"addressed_to": "", "belief_update": "", "argument": "短い意見です。"},
                {"addressed_to": "", "belief_update": "", "argument": "短い意見です。"},
            ],
            [
                {"addressed_to": "田中さん", "belief_update": "田中さんの指摘で考えが変わった", "argument": "もっと長い意見。この問題について詳しく考えてみると様々な視点があります。"},
                {"addressed_to": "鈴木さん", "belief_update": "鈴木さんの意見は参考になりました", "argument": "賛否両方の意見をよく吟味した上で最終的な立場を決めました。"},
            ],
        ]
    }


class TestDeliberationDepth:
    def test_deliberation_depth_all_engaged(self):
        """全員が addressed_to を記入、belief_update あり → 高スコア (> 0.6)"""
        meeting_result = _make_full_engagement_meeting()
        score = deliberation_depth(meeting_result)
        assert score > 0.6, f"Expected score > 0.6, got {score}"

    def test_deliberation_depth_no_engagement(self):
        """addressed_to 空、belief_update 空 → 低スコア (< 0.4)"""
        meeting_result = _make_no_engagement_meeting()
        score = deliberation_depth(meeting_result)
        assert score < 0.4, f"Expected score < 0.4, got {score}"

    def test_deliberation_depth_mixed(self):
        """一部エンゲージ → 中程度スコア (0.0 < score < 1.0)"""
        meeting_result = _make_mixed_engagement_meeting()
        score = deliberation_depth(meeting_result)
        assert 0.0 < score < 1.0, f"Expected 0 < score < 1, got {score}"

    def test_deliberation_depth_in_range(self):
        """返り値は 0.0〜1.0 の範囲"""
        for meeting in [
            _make_no_engagement_meeting(),
            _make_full_engagement_meeting(),
            _make_mixed_engagement_meeting(),
        ]:
            score = deliberation_depth(meeting)
            assert 0.0 <= score <= 1.0, f"Out of range: {score}"

    def test_deliberation_depth_empty_rounds(self):
        """rounds が空 → 0.0"""
        assert deliberation_depth({"rounds": []}) == 0.0

    def test_deliberation_depth_missing_rounds_key(self):
        """rounds キーなし → 0.0"""
        assert deliberation_depth({}) == 0.0

    def test_deliberation_depth_single_round(self):
        """Round が1つだけ → addressed_to/belief_update を評価できる"""
        meeting = {
            "rounds": [
                [
                    {"addressed_to": "田中さん", "belief_update": "考えが変わった", "argument": "長い意見です。" * 5},
                ]
            ]
        }
        score = deliberation_depth(meeting)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# evaluate_society_simulation 統合テスト
# ---------------------------------------------------------------------------

class TestEvaluateSocietySimulationExtended:
    @pytest.mark.asyncio
    async def test_evaluate_includes_demographic_representativeness(self):
        """evaluate_society_simulation が demographic_representativeness を含む"""
        agents = _make_agents_uniform()
        responses = [
            {"stance": "賛成", "confidence": 0.7, "reason": "具体的な理由。" * 15}
            for _ in range(40)
        ]
        meeting_result = _make_full_engagement_meeting()
        metrics = await evaluate_society_simulation(
            agents,
            responses,
            target_marginals=TARGET_UNIFORM,
            meeting_result=meeting_result,
        )
        metric_names = {m["metric_name"] for m in metrics}
        assert "demographic_representativeness" in metric_names

    @pytest.mark.asyncio
    async def test_evaluate_includes_response_quality(self):
        """evaluate_society_simulation が response_quality を含む"""
        agents = _make_agents_uniform()
        responses = [_make_good_response(200) for _ in range(40)]
        meeting_result = _make_full_engagement_meeting()
        metrics = await evaluate_society_simulation(
            agents,
            responses,
            target_marginals=TARGET_UNIFORM,
            meeting_result=meeting_result,
        )
        metric_names = {m["metric_name"] for m in metrics}
        assert "response_quality" in metric_names

    @pytest.mark.asyncio
    async def test_evaluate_includes_deliberation_depth(self):
        """evaluate_society_simulation が deliberation_depth を含む"""
        agents = _make_agents_uniform()
        responses = [_make_good_response(200) for _ in range(40)]
        meeting_result = _make_full_engagement_meeting()
        metrics = await evaluate_society_simulation(
            agents,
            responses,
            target_marginals=TARGET_UNIFORM,
            meeting_result=meeting_result,
        )
        metric_names = {m["metric_name"] for m in metrics}
        assert "deliberation_depth" in metric_names

    @pytest.mark.asyncio
    async def test_evaluate_backward_compatible_no_new_params(self):
        """既存の呼び出し方（新パラメータなし）でも動作する"""
        agents = [{"big_five": {"O": 0.5}, "values": {}} for _ in range(5)]
        responses = [{"stance": "中立", "confidence": 0.5, "reason": ""} for _ in range(5)]
        # 新パラメータを渡さない → 既存メトリクスのみ返す
        metrics = await evaluate_society_simulation(agents, responses)
        metric_names = {m["metric_name"] for m in metrics}
        # 既存メトリクスは引き続き存在する
        assert "diversity" in metric_names
        assert "consistency" in metric_names
        assert "calibration" in metric_names

    @pytest.mark.asyncio
    async def test_all_new_metric_scores_in_range(self):
        """新規メトリクスのスコアが全て 0.0〜1.0 範囲内"""
        agents = _make_agents_uniform()
        responses = [_make_good_response(200) for _ in range(40)]
        meeting_result = _make_full_engagement_meeting()
        metrics = await evaluate_society_simulation(
            agents,
            responses,
            target_marginals=TARGET_UNIFORM,
            meeting_result=meeting_result,
        )
        new_metric_names = {"demographic_representativeness", "response_quality", "deliberation_depth"}
        for m in metrics:
            if m["metric_name"] in new_metric_names:
                assert 0.0 <= m["score"] <= 1.0, (
                    f"{m['metric_name']} score {m['score']} out of [0, 1]"
                )


# ---------------------------------------------------------------------------
# Phase 6-2: detect_provider_bias
# ---------------------------------------------------------------------------

class TestDetectProviderBias:
    def test_provider_bias_detects_significant_diff(self):
        """OpenAI agents が全員"賛成"、Gemini agents が全員"反対" → bias_detected=True"""
        biased_agents = (
            [{"llm_backend": "openai"} for _ in range(20)]
            + [{"llm_backend": "gemini"} for _ in range(20)]
        )
        biased_responses = (
            [{"stance": "賛成", "confidence": 0.8} for _ in range(20)]
            + [{"stance": "反対", "confidence": 0.8} for _ in range(20)]
        )
        result = detect_provider_bias(biased_agents, biased_responses)
        assert result["bias_detected"] is True, (
            f"Expected bias_detected=True, got {result}"
        )

    def test_provider_bias_no_diff(self):
        """全プロバイダで同じ分布 → bias_detected=False"""
        unbiased_agents = (
            [{"llm_backend": "openai"} for _ in range(20)]
            + [{"llm_backend": "gemini"} for _ in range(20)]
        )
        unbiased_responses = [
            {"stance": "賛成" if i % 2 == 0 else "反対", "confidence": 0.7}
            for i in range(40)
        ]
        result = detect_provider_bias(unbiased_agents, unbiased_responses)
        assert result["bias_detected"] is False, (
            f"Expected bias_detected=False, got {result}"
        )

    def test_provider_bias_returns_required_keys(self):
        """返り値に bias_detected, p_value, provider_distributions が含まれる"""
        agents = [{"llm_backend": "openai"} for _ in range(10)]
        responses = [{"stance": "賛成", "confidence": 0.7} for _ in range(10)]
        result = detect_provider_bias(agents, responses)
        assert "bias_detected" in result
        assert "p_value" in result
        assert "provider_distributions" in result

    def test_provider_bias_p_value_is_float(self):
        """p_value は float 型"""
        agents = [{"llm_backend": "openai"} for _ in range(10)]
        responses = [{"stance": "賛成", "confidence": 0.7} for _ in range(10)]
        result = detect_provider_bias(agents, responses)
        assert isinstance(result["p_value"], float)

    def test_provider_bias_p_value_in_range(self):
        """p_value は 0.0〜1.0 の範囲"""
        biased_agents = (
            [{"llm_backend": "openai"} for _ in range(20)]
            + [{"llm_backend": "gemini"} for _ in range(20)]
        )
        biased_responses = (
            [{"stance": "賛成", "confidence": 0.8} for _ in range(20)]
            + [{"stance": "反対", "confidence": 0.8} for _ in range(20)]
        )
        result = detect_provider_bias(biased_agents, biased_responses)
        assert 0.0 <= result["p_value"] <= 1.0

    def test_provider_bias_provider_distributions_structure(self):
        """provider_distributions はプロバイダ名 → スタンス分布の dict"""
        biased_agents = (
            [{"llm_backend": "openai"} for _ in range(20)]
            + [{"llm_backend": "gemini"} for _ in range(20)]
        )
        biased_responses = (
            [{"stance": "賛成", "confidence": 0.8} for _ in range(20)]
            + [{"stance": "反対", "confidence": 0.8} for _ in range(20)]
        )
        result = detect_provider_bias(biased_agents, biased_responses)
        dists = result["provider_distributions"]
        assert isinstance(dists, dict)
        assert "openai" in dists
        assert "gemini" in dists
        # openai の分布は 賛成 が 1.0
        assert dists["openai"].get("賛成", 0.0) == pytest.approx(1.0, abs=1e-6)
        # gemini の分布は 反対 が 1.0
        assert dists["gemini"].get("反対", 0.0) == pytest.approx(1.0, abs=1e-6)

    def test_provider_bias_single_provider(self):
        """プロバイダが1種類のみ → bias_detected=False（比較不能）"""
        agents = [{"llm_backend": "openai"} for _ in range(20)]
        responses = [{"stance": "賛成", "confidence": 0.7} for _ in range(20)]
        result = detect_provider_bias(agents, responses)
        assert result["bias_detected"] is False

    def test_provider_bias_empty_inputs(self):
        """空のリスト → bias_detected=False、p_value=1.0"""
        result = detect_provider_bias([], [])
        assert result["bias_detected"] is False
        assert result["p_value"] == pytest.approx(1.0, abs=1e-9)
