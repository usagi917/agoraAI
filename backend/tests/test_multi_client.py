"""MultiLLMClient テスト: アダプタルーティング、バッチグループ化"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.app.llm.multi_client import MultiLLMClient, _extract_json


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"key": "value"}') == {"key": "value"}

    def test_json_in_markdown(self):
        text = '```json\n{"key": "value"}\n```'
        assert _extract_json(text) == {"key": "value"}

    def test_json_with_thinking_tags(self):
        text = '<think>some thought</think>{"key": "value"}'
        assert _extract_json(text) == {"key": "value"}

    def test_json_embedded_in_text(self):
        text = 'Here is the result: {"key": "value"} end'
        assert _extract_json(text) == {"key": "value"}

    def test_non_json(self):
        assert _extract_json("just plain text") is None

    def test_empty_string(self):
        assert _extract_json("") is None


class TestMultiLLMClientRouting:
    def test_available_providers_empty_without_keys(self):
        client = MultiLLMClient()
        with patch("src.app.llm.multi_client.settings") as mock_settings:
            mock_settings.load_llm_providers_config.return_value = {
                "providers": {
                    "openai": {
                        "type": "openai",
                        "model": "gpt-4o",
                        "api_base": "https://api.openai.com/v1",
                        "env_key": "NONEXISTENT_KEY_12345",
                        "enabled": True,
                        "rate_limit": {},
                    }
                },
                "fallback_order": ["openai"],
            }
            # No API key set
            with patch.dict("os.environ", {}, clear=False):
                mock_settings.nonexistent_key_12345 = ""
                client.initialize()
                assert client.available_providers() == []

    def test_fallback_when_provider_unavailable(self):
        client = MultiLLMClient()
        client._initialized = True
        client._adapters = {}
        client._fallback_order = []
        with pytest.raises(RuntimeError, match="No LLM providers available"):
            client._resolve_provider("nonexistent")

    def test_resolve_provider_with_fallback(self):
        client = MultiLLMClient()
        client._initialized = True

        mock_adapter = MagicMock()
        mock_limiter = MagicMock()
        client._adapters = {"openai": mock_adapter}
        client._rate_limiters = {"openai": mock_limiter}
        client._fallback_order = ["openai"]

        adapter, limiter = client._resolve_provider("gemini")
        assert adapter is mock_adapter
        assert limiter is mock_limiter


class TestMultiLLMClientBatch:
    @pytest.mark.asyncio
    async def test_call_batch_groups_by_provider(self):
        client = MultiLLMClient()
        client._initialized = True

        mock_adapter = AsyncMock()
        mock_adapter.call = AsyncMock(return_value=('{"stance": "neutral"}', {
            "model": "test",
            "provider": "openai",
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }))

        mock_limiter = MagicMock()
        mock_limiter.acquire = AsyncMock()
        mock_limiter.release = MagicMock()
        mock_limiter.record_usage = MagicMock()

        client._adapters = {"openai": mock_adapter}
        client._rate_limiters = {"openai": mock_limiter}
        client._fallback_order = ["openai"]

        calls = [
            {
                "provider": "openai",
                "system_prompt": "You are a test agent.",
                "user_prompt": "What do you think?",
                "temperature": 0.5,
                "max_tokens": 100,
            },
            {
                "provider": "openai",
                "system_prompt": "You are another agent.",
                "user_prompt": "Your opinion?",
                "temperature": 0.5,
                "max_tokens": 100,
            },
        ]

        results = await client.call_batch_by_provider(calls, max_concurrency=5)
        assert len(results) == 2
        assert mock_adapter.call.call_count == 2

    @pytest.mark.asyncio
    async def test_call_batch_handles_errors(self):
        client = MultiLLMClient()
        client._initialized = True

        mock_adapter = AsyncMock()
        mock_adapter.call = AsyncMock(side_effect=Exception("API error"))

        mock_limiter = MagicMock()
        mock_limiter.acquire = AsyncMock()
        mock_limiter.release = MagicMock()
        mock_limiter.record_usage = MagicMock()

        client._adapters = {"openai": mock_adapter}
        client._rate_limiters = {"openai": mock_limiter}
        client._fallback_order = ["openai"]

        calls = [
            {
                "provider": "openai",
                "system_prompt": "test",
                "user_prompt": "test",
            }
        ]

        results = await client.call_batch_by_provider(calls)
        assert len(results) == 1
        assert results[0][0]["_error"] is True  # error dict on failure
