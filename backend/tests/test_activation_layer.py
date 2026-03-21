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
        assert result["stance"] == "中立"
        assert result["confidence"] == 0.5

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
