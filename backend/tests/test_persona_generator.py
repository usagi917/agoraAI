"""ペルソナ生成テスト: activation 後のペルソナ生成と activation プロンプトの分離"""

import pytest
from unittest.mock import AsyncMock, patch

from src.app.services.society.persona_generator import (
    generate_persona_narratives_post_activation,
)
from src.app.services.society.activation_prompts import build_activation_prompt


def _make_agent(agent_id: str = "agent-1", stance: str = "賛成") -> dict:
    """テスト用ダミーエージェントを生成する。"""
    return {
        "id": agent_id,
        "demographics": {
            "age": 35,
            "region": "関東（都市部）",
            "gender": "male",
            "income_bracket": "middle",
            "occupation": "会社員",
            "education": "bachelor",
        },
        "big_five": {"O": 0.6, "C": 0.5, "E": 0.7, "A": 0.4, "N": 0.3},
        "values": {"security": 0.8, "freedom": 0.6, "innovation": 0.5},
        "shock_sensitivity": {"economy": 0.7},
        "life_event": "転職したばかり",
        "contradiction": "安定を求めつつ挑戦したい",
        "hidden_motivation": "家族の将来が不安",
        "speech_style": "率直で簡潔",
        "information_source": "新聞",
    }


def _make_response(stance: str = "賛成", confidence: float = 0.8) -> dict:
    """テスト用 activation レスポンスを生成する。"""
    return {
        "stance": stance,
        "confidence": confidence,
        "reason": "物価高騰で家計が厳しいから",
        "personal_story": "先月のスーパーの値段が上がっていた",
        "concern": "将来の貯金が心配",
        "priority": "生活費の安定",
    }


class TestPostActivationPersona:
    """activation 後のペルソナ生成テスト。"""

    @pytest.mark.asyncio
    async def test_post_activation_persona_includes_stance(self):
        """生成されたナラティブにスタンス情報が含まれる。"""
        agents = [_make_agent()]
        responses = [_make_response(stance="賛成")]

        # Mock the LLM to return a narrative mentioning the stance
        mock_narrative = "私は賛成の立場です。転職したばかりの会社員として、この政策は家計に良い影響を与えると考えています。"

        with patch("src.app.services.society.persona_generator.multi_llm_client") as mock_client:
            mock_client.initialize = lambda: None
            mock_client.call_batch_by_provider = AsyncMock(
                return_value=[(mock_narrative, {"total_tokens": 100})]
            )
            result = await generate_persona_narratives_post_activation(
                agents, responses, "消費税増税について"
            )

        assert result[0].get("persona_narrative"), "Persona narrative should be set"
        # Verify the LLM was called with stance information in the prompt
        call_args = mock_client.call_batch_by_provider.call_args
        calls_list = call_args[0][0]  # first positional arg
        user_prompt = calls_list[0]["user_prompt"]
        assert "賛成" in user_prompt, "Stance should be included in LLM prompt"

    @pytest.mark.asyncio
    async def test_provider_override_keeps_bounded_narratives_local(self):
        agents = [_make_agent()]
        responses = [_make_response()]

        with patch("src.app.services.society.persona_generator.multi_llm_client") as mock_client:
            mock_client.initialize = lambda: None
            mock_client.call_batch_by_provider = AsyncMock(
                return_value=[("私は地域の生活者です。", {"total_tokens": 20})]
            )
            await generate_persona_narratives_post_activation(
                agents,
                responses,
                "テスト政策",
                provider_override="liquid",
            )

        calls = mock_client.call_batch_by_provider.call_args.args[0]
        assert calls[0]["provider"] == "liquid"

    @pytest.mark.asyncio
    async def test_activation_prompt_no_persona_leak(self):
        """activation プロンプトに persona_narrative が含まれない。"""
        agent = _make_agent()
        # Set a persona_narrative that should NOT appear in activation prompt
        agent["persona_narrative"] = "これは古いペルソナです。"

        system_prompt, user_prompt = build_activation_prompt(
            agent, "消費税増税について"
        )

        combined = system_prompt + user_prompt
        assert "これは古いペルソナです。" not in combined, (
            "Activation prompt should not contain persona_narrative"
        )

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(self):
        """LLM エラー時に空ナラティブで正常続行する。"""
        agents = [_make_agent(), _make_agent(agent_id="agent-2")]
        responses = [_make_response(), _make_response(stance="反対")]

        with patch("src.app.services.society.persona_generator.multi_llm_client") as mock_client:
            mock_client.initialize = lambda: None
            # First call succeeds, second raises exception
            mock_client.call_batch_by_provider = AsyncMock(
                return_value=[
                    (Exception("LLM error"), {"total_tokens": 0}),
                    (Exception("LLM error"), {"total_tokens": 0}),
                ]
            )
            result = await generate_persona_narratives_post_activation(
                agents, responses, "テスト"
            )

        # Should not raise, all agents should have (possibly empty) persona_narrative
        assert len(result) == 2
        for agent in result:
            assert "persona_narrative" in agent
