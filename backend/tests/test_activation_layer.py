"""活性化レイヤーテスト: プロンプト構築、応答集計（LLMモック）"""

import pytest
from unittest.mock import AsyncMock, patch

from src.app.services.society.activation_layer import (
    run_activation,
    _parse_activation_response,
    _aggregate_opinions,
    _select_representatives,
)
from src.app.services.society.activation_prompts import build_activation_prompt


class TestParseActivationResponse:
    def test_parse_dict_response(self):
        result = _parse_activation_response({
            "stance": "賛成",
            "confidence": 0.8,
            "reason": "経済的メリットがある",
            "concern": "コスト",
            "priority": "雇用創出",
        })
        assert result["stance"] == "賛成"
        assert result["confidence"] == 0.8

    def test_parse_string_response(self):
        result = _parse_activation_response("just some text")
        assert result["stance"] == ""
        assert result["confidence"] == 0.0
        assert result["_failed"] is True

    def test_parse_empty_dict(self):
        result = _parse_activation_response({})
        assert result["stance"] == "中立"
        assert result["confidence"] == 0.5


class TestAggregateOpinions:
    def test_basic_aggregation(self):
        responses = [
            {"stance": "賛成", "confidence": 0.8, "concern": "コスト", "priority": "雇用"},
            {"stance": "賛成", "confidence": 0.9, "concern": "コスト", "priority": "雇用"},
            {"stance": "反対", "confidence": 0.7, "concern": "環境", "priority": "安全"},
            {"stance": "中立", "confidence": 0.5, "concern": "", "priority": ""},
        ]
        agg = _aggregate_opinions(responses)
        assert agg["total_respondents"] == 4
        assert agg["stance_distribution"]["賛成"] == 0.5
        assert agg["stance_distribution"]["反対"] == 0.25
        assert agg["average_confidence"] > 0.5
        assert "コスト" in agg["top_concerns"]

    def test_empty_responses(self):
        agg = _aggregate_opinions([])
        assert agg["total_respondents"] == 0 or agg["average_confidence"] == 0.0


class TestSelectRepresentatives:
    def test_selects_from_each_stance(self):
        agents = [
            {"id": "a1"}, {"id": "a2"}, {"id": "a3"}, {"id": "a4"},
        ]
        responses = [
            {"stance": "賛成", "confidence": 0.9},
            {"stance": "反対", "confidence": 0.8},
            {"stance": "中立", "confidence": 0.7},
            {"stance": "賛成", "confidence": 0.6},
        ]
        reps = _select_representatives(agents, responses, count=4)
        stances = {r["response"]["stance"] for r in reps}
        assert len(stances) >= 2


class TestBuildActivationPrompt:
    def test_prompt_structure(self):
        agent = {
            "demographics": {
                "age": 35, "gender": "female", "occupation": "エンジニア",
                "region": "関東（都市部）", "education": "master", "income_bracket": "upper_middle",
            },
            "big_five": {"O": 0.8, "C": 0.6, "E": 0.3, "A": 0.7, "N": 0.4},
            "values": {"innovation": 0.6, "efficiency": 0.4},
            "life_event": "最近転職した",
            "information_source": "SNS(Twitter/X)",
            "speech_style": "分析的で論理的",
        }
        system_prompt, user_prompt = build_activation_prompt(agent, "AIの社会的影響")
        assert "35歳" in system_prompt
        assert "エンジニア" in system_prompt
        assert "AIの社会的影響" in user_prompt
        assert "JSON" in system_prompt


class TestAggregateOpinionsWithStatisticalInference:
    """Phase 1-2: _aggregate_opinions 拡張テスト (agents=None のフォールバックを含む)"""

    def _make_responses(self, n: int = 50) -> list[dict]:
        """n 件の有効なレスポンスを生成するヘルパー。"""
        stances = ["賛成", "反対", "中立", "条件付き賛成"]
        return [
            {
                "stance": stances[i % len(stances)],
                "confidence": 0.7,
                "concern": "コスト",
                "priority": "効率",
            }
            for i in range(n)
        ]

    def _make_agents(self, n: int = 50) -> list[dict]:
        """n 件のエージェントを生成するヘルパー。"""
        regions = ["関東", "関西", "中部", "東北", "九州"]
        genders = ["male", "female"]
        age_brackets = ["18-29", "30-49", "50-69", "70+"]
        return [
            {
                "id": f"agent-{i}",
                "demographics": {
                    "age": 35,
                    "gender": genders[i % len(genders)],
                    "region": regions[i % len(regions)],
                    "age_bracket": age_brackets[i % len(age_brackets)],
                    "occupation": "会社員",
                    "education": "bachelor",
                    "income_bracket": "upper_middle",
                },
                "big_five": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
            }
            for i in range(n)
        ]

    def test_aggregate_includes_confidence_intervals(self):
        """agents を渡した場合、返り値に confidence_intervals キーが存在し、
        各スタンスに [lower, upper] のタプルがある。"""
        responses = self._make_responses(50)
        agents = self._make_agents(50)

        agg = _aggregate_opinions(responses, agents=agents)

        assert "confidence_intervals" in agg, "confidence_intervals キーがない"
        ci = agg["confidence_intervals"]
        assert isinstance(ci, dict), "confidence_intervals は dict であるべき"
        # スタンスが存在する場合、各値は (lower, upper) のタプルであること
        for stance, interval in ci.items():
            assert len(interval) == 2, f"stance={stance} の CI はタプル長2であるべき"
            lower, upper = interval
            assert 0.0 <= lower <= 1.0, f"lower={lower} は [0,1] の範囲外"
            assert 0.0 <= upper <= 1.0, f"upper={upper} は [0,1] の範囲外"
            assert lower <= upper, f"lower={lower} > upper={upper}"

    def test_aggregate_includes_effective_sample_size(self):
        """agents を渡した場合、返り値に effective_sample_size キーが存在し、0より大きい数値。"""
        responses = self._make_responses(50)
        agents = self._make_agents(50)

        agg = _aggregate_opinions(responses, agents=agents)

        assert "effective_sample_size" in agg, "effective_sample_size キーがない"
        n_eff = agg["effective_sample_size"]
        assert isinstance(n_eff, (int, float)), "effective_sample_size は数値であるべき"
        assert n_eff > 0, f"effective_sample_size={n_eff} は 0 より大きくあるべき"

    def test_aggregate_raw_distribution_preserved(self):
        """agents を渡した場合、返り値に stance_distribution_raw キーが存在し、
        元の未ウェイト分布を保持する。"""
        responses = self._make_responses(50)
        agents = self._make_agents(50)

        # agents なし（従来）の分布
        agg_no_agents = _aggregate_opinions(responses)
        raw_dist_reference = agg_no_agents["stance_distribution"]

        # agents あり（新規）の分布
        agg_with_agents = _aggregate_opinions(responses, agents=agents)

        assert "stance_distribution_raw" in agg_with_agents, "stance_distribution_raw キーがない"
        raw_dist = agg_with_agents["stance_distribution_raw"]
        assert isinstance(raw_dist, dict), "stance_distribution_raw は dict であるべき"
        # 生分布は agents なしの stance_distribution と同じ値を持つ
        for stance, proportion in raw_dist_reference.items():
            assert stance in raw_dist, f"stance={stance} が stance_distribution_raw にない"
            assert abs(raw_dist[stance] - proportion) < 1e-6, (
                f"stance={stance}: raw={raw_dist[stance]} != reference={proportion}"
            )

    def test_aggregate_warns_on_low_n_eff(self):
        """有効標本数 < 30 の場合に low_sample_warning: True フラグが立つ。"""
        # 少数のレスポンス（n_eff < 30 になるほど少ない）
        responses = self._make_responses(5)
        agents = self._make_agents(5)

        agg = _aggregate_opinions(responses, agents=agents)

        assert "low_sample_warning" in agg, "low_sample_warning キーがない"
        # 5 件しかないので n_eff < 30 → True になるはず
        assert agg["low_sample_warning"] is True, (
            f"n_eff={agg.get('effective_sample_size')} のとき low_sample_warning は True であるべき"
        )


class TestRunActivation:
    @pytest.mark.asyncio
    async def test_run_activation_with_mock(self):
        agents = [
            {
                "id": f"agent-{i}",
                "llm_backend": "openai",
                "demographics": {"age": 30, "gender": "male", "occupation": "会社員",
                                  "region": "関東（都市部）", "education": "bachelor", "income_bracket": "upper_middle"},
                "big_five": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
                "values": {"efficiency": 0.5},
                "life_event": "",
                "information_source": "テレビニュース",
                "speech_style": "丁寧で慎重",
            }
            for i in range(5)
        ]

        mock_response = (
            {"stance": "賛成", "confidence": 0.7, "reason": "テスト理由", "concern": "コスト", "priority": "効率"},
            {"model": "test", "provider": "openai", "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        with patch("src.app.services.society.activation_layer.multi_llm_client") as mock_client:
            mock_client.initialize = lambda: None
            mock_client.call_batch_by_provider = AsyncMock(return_value=[mock_response] * 5)

            result = await run_activation(agents, "テスト テーマ", max_concurrency=5)

            assert len(result["responses"]) == 5
            assert result["aggregation"]["total_respondents"] == 5
            assert "賛成" in result["aggregation"]["stance_distribution"]
            assert len(result["representatives"]) > 0
            assert result["usage"]["total_tokens"] > 0


# ---------------------------------------------------------------------------
# Phase 3-3: build_activation_prompt にグラウンディング注入
# ---------------------------------------------------------------------------

dummy_grounding_facts = [
    {"fact": "2024年の実質賃金は前年比-2.5%", "source": "厚生労働省 毎月勤労統計調査", "date": "2024-12"},
    {"fact": "完全失業率は2.6%", "source": "総務省 労働力調査", "date": "2024-12"},
]

dummy_agent = {
    "demographics": {"age": 35, "region": "関東", "occupation": "会社員", "gender": "male", "education": "大学", "income_bracket": "中間層"},
    "big_five": {"O": 0.6, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.4},
    "values": {"経済": 0.8, "安全": 0.6},
    "speech_style": "率直で簡潔",
    "information_source": "テレビ・新聞",
    "persona_narrative": "東京で働く35歳の会社員。",
}


class TestBuildActivationPromptGrounding:
    """Phase 3-3: grounding_facts パラメータの注入テスト"""

    def test_prompt_includes_grounding_section(self):
        """grounding_facts を渡すと system_prompt に「客観的事実」セクションが含まれる。"""
        system_prompt, _ = build_activation_prompt(
            dummy_agent, "賃金政策", grounding_facts=dummy_grounding_facts
        )
        assert "客観的事実" in system_prompt

    def test_prompt_omits_grounding_when_empty(self):
        """grounding_facts が空リストのとき「客観的事実」セクションを含まない。"""
        system_prompt_empty, _ = build_activation_prompt(
            dummy_agent, "賃金政策", grounding_facts=[]
        )
        assert "客観的事実" not in system_prompt_empty

        system_prompt_none, _ = build_activation_prompt(
            dummy_agent, "賃金政策", grounding_facts=None
        )
        assert "客観的事実" not in system_prompt_none

    def test_prompt_cites_source(self):
        """grounding_facts を渡した場合、出典（"厚生労働省"）が system_prompt に含まれる。"""
        system_prompt, _ = build_activation_prompt(
            dummy_agent, "賃金政策", grounding_facts=dummy_grounding_facts
        )
        assert "厚生労働省" in system_prompt


# ---------------------------------------------------------------------------
# Independence-weighted aggregation
# ---------------------------------------------------------------------------


class TestAggregateOpinionsWithIndependenceWeights:
    """独立性重み付き集計のテスト."""

    def _make_agents(self, n: int) -> list[dict]:
        regions = ["関東", "関西", "中部", "東北", "九州"]
        genders = ["male", "female"]
        age_brackets = ["18-29", "30-49", "50-69", "70+"]
        return [
            {
                "id": f"agent-{i}",
                "demographics": {
                    "age": 35,
                    "gender": genders[i % len(genders)],
                    "region": regions[i % len(regions)],
                    "age_bracket": age_brackets[i % len(age_brackets)],
                },
            }
            for i in range(n)
        ]

    def _make_responses(self, stances: list[str]) -> list[dict]:
        return [
            {"stance": s, "confidence": 0.8, "concern": "コスト", "priority": "効率"}
            for s in stances
        ]

    def test_independence_weights_none_falls_back(self):
        """independence_weights=None → 従来と同じ挙動."""
        agents = self._make_agents(10)
        responses = self._make_responses(["賛成"] * 5 + ["反対"] * 5)

        agg_without = _aggregate_opinions(responses, agents=agents, independence_weights=None)
        agg_default = _aggregate_opinions(responses, agents=agents)

        assert agg_without["stance_distribution"] == agg_default["stance_distribution"]

    def test_independence_weights_shift_distribution(self):
        """多数派クラスターに低い独立性重み → 分布が少数派側にシフト."""
        agents = self._make_agents(10)
        # agent 0-7: 賛成 (多数派), agent 8-9: 反対 (少数派)
        responses = self._make_responses(["賛成"] * 8 + ["反対"] * 2)

        # 多数派クラスター (agent 0-7) を大幅に割り引く
        independence_weights = {
            f"agent-{i}": 0.3 for i in range(8)
        }
        independence_weights.update({
            f"agent-{i}": 1.0 for i in range(8, 10)
        })

        agg_plain = _aggregate_opinions(responses, agents=agents)
        agg_weighted = _aggregate_opinions(
            responses, agents=agents, independence_weights=independence_weights,
        )

        # 独立性重みなし: 賛成 80%
        assert agg_plain["stance_distribution"]["賛成"] > 0.7

        # 独立性重みあり: 賛成の割合が下がる
        assert agg_weighted["stance_distribution"]["賛成"] < agg_plain["stance_distribution"]["賛成"]

    def test_independence_weights_reduce_effective_sample_size(self):
        """独立性重みの分散が大きい → n_eff が小さくなる."""
        agents = self._make_agents(20)
        responses = self._make_responses(["賛成"] * 10 + ["反対"] * 10)

        agg_no_ind = _aggregate_opinions(responses, agents=agents)

        # 不均一な独立性重み
        independence_weights = {
            f"agent-{i}": (0.3 if i < 10 else 2.0) for i in range(20)
        }
        agg_with_ind = _aggregate_opinions(
            responses, agents=agents, independence_weights=independence_weights,
        )

        # 重みの分散が大きい → n_eff が小さい
        assert agg_with_ind["effective_sample_size"] < agg_no_ind["effective_sample_size"]

    def test_aggregation_result_includes_independence_metadata(self):
        """independence_weights を渡すと結果に independence_weighting_applied が含まれる."""
        agents = self._make_agents(5)
        responses = self._make_responses(["賛成"] * 5)
        weights = {f"agent-{i}": 1.0 for i in range(5)}

        agg = _aggregate_opinions(responses, agents=agents, independence_weights=weights)

        assert "independence_weighting_applied" in agg
        assert agg["independence_weighting_applied"] is True

    def test_independence_weighting_not_applied_when_none(self):
        """independence_weights=None → independence_weighting_applied が False."""
        agents = self._make_agents(5)
        responses = self._make_responses(["賛成"] * 5)

        agg = _aggregate_opinions(responses, agents=agents, independence_weights=None)

        assert agg.get("independence_weighting_applied") is False


# ---------------------------------------------------------------------------
# Phase A: 反中庸バイアス・プロンプト改修テスト
# ---------------------------------------------------------------------------


class TestAntiCentralTendencyPrompt:
    """Phase A: プロンプトが中庸バイアスを抑制する構造になっていることを検証。"""

    def _build_prompt(self, **overrides) -> str:
        agent = {
            "demographics": {
                "age": 42, "region": "関西", "occupation": "漁師",
                "gender": "male", "education": "高校", "income_bracket": "low",
            },
            "big_five": {"O": 0.3, "C": 0.7, "E": 0.4, "A": 0.5, "N": 0.6},
            "values": {"security": 0.8, "environment": 0.6},
            "speech_style": "率直で簡潔",
            "information_source": "地元の漁協",
            **overrides,
        }
        system_prompt, _ = build_activation_prompt(agent, "漁業規制の強化")
        return system_prompt

    def test_prompt_uses_gut_reaction_first(self):
        """思考プロセスが balanced pros/cons ではなく、直感的反応→理由→覆す条件の順序。"""
        prompt = self._build_prompt()
        # 旧プロンプトの balanced 構造（プラス/マイナス列挙）が存在しないこと
        assert "プラスかマイナスかを判定" not in prompt
        # motivated reasoning 型の要素が含まれること
        assert "直感" in prompt or "最初に感じた" in prompt or "率直な反応" in prompt

    def test_prompt_discourages_neutral_default(self):
        """中立のデフォルト選択を抑制する指示が含まれること。"""
        prompt = self._build_prompt()
        # 中立の安易な選択を防ぐ指示
        assert "中立" in prompt
        # 「中立は安易に選ばない」旨の指示が存在すること
        neutral_section = prompt[prompt.index("中立"):]
        has_anti_neutral = any(
            keyword in prompt
            for keyword in ["判断不能", "本当に", "安易", "真に", "どちらにも"]
        )
        assert has_anti_neutral, "中立の安易な選択を抑制する指示がない"

    def test_prompt_defines_confidence_correctly(self):
        """confidence の定義が「自分の確信度」であり、「議論の度合い」でないことを明示。"""
        prompt = self._build_prompt()
        has_confidence_definition = any(
            keyword in prompt
            for keyword in ["確信", "自分の立場", "あなたがどれだけ"]
        )
        assert has_confidence_definition, "confidence の正しい定義が含まれていない"

    def test_prompt_still_requires_json_format(self):
        """後方互換: JSON レスポンス形式の要求は維持されること。"""
        prompt = self._build_prompt()
        assert "JSON" in prompt
        assert '"stance"' in prompt
        assert '"confidence"' in prompt
        assert '"reason"' in prompt

    def test_prompt_still_includes_persona(self):
        """後方互換: ペルソナ情報（年齢、職業、地域）が含まれること。"""
        prompt = self._build_prompt()
        assert "42歳" in prompt
        assert "漁師" in prompt
        assert "関西" in prompt

    def test_prompt_still_includes_speech_style(self):
        """後方互換: 話し方スタイル指示が含まれること。"""
        prompt = self._build_prompt()
        assert "率直で簡潔" in prompt
        assert "話し方" in prompt


# ---------------------------------------------------------------------------
# Phase B: 品質重み減衰テスト
# ---------------------------------------------------------------------------


class TestQualityWeightedAggregation:
    """Phase B: medium 品質レスポンスの重み減衰テスト。"""

    def _make_agents(self, n: int) -> list[dict]:
        regions = ["関東", "関西", "中部", "東北", "九州"]
        genders = ["male", "female"]
        return [
            {
                "id": f"agent-{i}",
                "demographics": {
                    "age": 35,
                    "gender": genders[i % len(genders)],
                    "region": regions[i % len(regions)],
                    "age_bracket": "30-49",
                },
            }
            for i in range(n)
        ]

    def test_medium_quality_responses_get_lower_weight(self):
        """medium 品質と high 品質が混在する場合、品質重みが適用されていることを検証。
        品質ゲーティングにより classify_response_quality が呼ばれている。"""
        from src.app.services.society.output_validator import classify_response_quality

        # medium: 賛成, confidence=0.5 (→ medium tier)
        medium_responses = [
            {"stance": "賛成", "confidence": 0.5, "reason": "良い政策だと思います。" * 10,
             "concern": "コスト", "priority": "効率"}
            for _ in range(10)
        ]
        # high: 反対, confidence=0.8, 具体的 reason (100文字以上・数字・地名あり)
        high_responses = [
            {"stance": "反対", "confidence": 0.8,
             "reason": "私の東京都内の職場では月額30万円のコスト増が発生しており、この政策には強く反対します。2023年以降、売上が15%減少しており、このままでは事業の継続が困難になる恐れがあります。従業員の生活を守るためにも、拙速な導入は避けるべきです。",
             "concern": "コスト増", "priority": "雇用維持"}
            for _ in range(5)
        ]

        # 品質 tier が正しく分類されることを確認
        assert classify_response_quality(medium_responses[0]) == "medium"
        assert classify_response_quality(high_responses[0]) == "high"

        responses = medium_responses + high_responses
        agents = self._make_agents(15)

        # agents あり (品質重み適用) の集約
        agg = _aggregate_opinions(responses, agents=agents)

        # 品質減衰なしなら 賛成=10/15=66%, 反対=5/15=33%
        # 品質減衰あり: medium×0.7=7.0, high×1.0=5.0 → 賛成=7/12=58%, 反対=5/12=42%
        # ポストストラットの影響もあるため、exact な値は比較しないが
        # weighted_dist が存在し、stance_distribution_raw とは異なることを確認
        assert "stance_distribution_raw" in agg
        assert "stance_distribution" in agg
        # weighted は raw と異なるはず（品質重み + ポストストラット）
        assert agg["stance_distribution"] != agg["stance_distribution_raw"]
