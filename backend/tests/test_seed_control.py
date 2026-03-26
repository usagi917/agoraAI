"""シード制御 + LLM クライアント統合テスト"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx


class TestOpenAIAdapterSeed:
    """OpenAI アダプタが seed パラメータを API リクエストに含めること。"""

    @pytest.mark.asyncio
    async def test_call_with_seed_includes_seed_in_body(self):
        from src.app.llm.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter("test", {"model": "gpt-4o", "api_base": "http://test"})
        adapter.api_key = "test-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test response"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter, "_get_http_client") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)
            content, usage = await adapter.call(
                "system", "user", temperature=0.5, max_tokens=100, seed=42,
            )

        call_kwargs = mock_client.return_value.post.call_args
        body = call_kwargs.kwargs["json"]
        assert body["seed"] == 42

    @pytest.mark.asyncio
    async def test_call_without_seed_omits_seed_from_body(self):
        from src.app.llm.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter("test", {"model": "gpt-4o", "api_base": "http://test"})
        adapter.api_key = "test-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter, "_get_http_client") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)
            await adapter.call("system", "user", temperature=0.5, max_tokens=100)

        call_kwargs = mock_client.return_value.post.call_args
        body = call_kwargs.kwargs["json"]
        assert "seed" not in body


class TestMultiLLMClientSeed:
    """MultiLLMClient が seed を adapter に伝搬すること。"""

    @pytest.mark.asyncio
    async def test_call_passes_seed_to_adapter(self):
        from src.app.llm.multi_client import MultiLLMClient

        client = MultiLLMClient()
        mock_adapter = MagicMock()
        mock_adapter.call = AsyncMock(return_value=('{"result": "ok"}', {"total_tokens": 10}))
        mock_limiter = MagicMock()
        mock_limiter.acquire = AsyncMock()
        mock_limiter.release = MagicMock()
        mock_limiter.record_usage = MagicMock()

        client._adapters = {"test": mock_adapter}
        client._rate_limiters = {"test": mock_limiter}
        client._initialized = True

        await client.call("test", "sys", "user", seed=42)

        mock_adapter.call.assert_called_once_with(
            "sys", "user", 0.5, 1024, seed=42,
        )

    @pytest.mark.asyncio
    async def test_call_without_seed_passes_none(self):
        from src.app.llm.multi_client import MultiLLMClient

        client = MultiLLMClient()
        mock_adapter = MagicMock()
        mock_adapter.call = AsyncMock(return_value=('{"result": "ok"}', {"total_tokens": 10}))
        mock_limiter = MagicMock()
        mock_limiter.acquire = AsyncMock()
        mock_limiter.release = MagicMock()
        mock_limiter.record_usage = MagicMock()

        client._adapters = {"test": mock_adapter}
        client._rate_limiters = {"test": mock_limiter}
        client._initialized = True

        await client.call("test", "sys", "user")

        mock_adapter.call.assert_called_once_with(
            "sys", "user", 0.5, 1024, seed=None,
        )


class TestAnthropicAdapterSeed:
    """Anthropic アダプタは seed を metadata として含める。"""

    @pytest.mark.asyncio
    async def test_call_with_seed_includes_metadata(self):
        from src.app.llm.adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter("test", {"model": "claude-sonnet-4-20250514", "api_base": "http://test"})
        adapter.api_key = "test-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "test response"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter, "_get_http_client") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)
            content, usage = await adapter.call(
                "system", "user", temperature=0.5, max_tokens=100, seed=42,
            )

        # Anthropic は seed をネイティブサポートしないが、usage に記録
        assert usage.get("seed") == 42
