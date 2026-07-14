import pytest

from src.app.llm.adapters.openai_adapter import OpenAIAdapter


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self):
        self.last_url = ""
        self.last_json = None
        self.last_headers = None
        self.is_closed = False

    async def post(self, url: str, json: dict, headers: dict):
        self.last_url = url
        self.last_json = json
        self.last_headers = headers
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"ok": true}',
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            }
        )


@pytest.mark.asyncio
async def test_openai_adapter_skips_temperature_for_reasoning_models(caplog):
    adapter = OpenAIAdapter(
        "openai",
        {
            "model": "gpt-5-nano-2025-08-07",
            "api_base": "https://api.openai.com/v1",
        },
    )
    adapter.api_key = "test-key"
    fake_http_client = _FakeAsyncClient()
    adapter._http_client = fake_http_client

    with caplog.at_level("INFO"):
        content, usage = await adapter.call(
            system_prompt="sys",
            user_prompt="user",
            temperature=0.7,
            max_tokens=128,
        )

    assert fake_http_client.last_url.endswith("/chat/completions")
    assert fake_http_client.last_json["max_completion_tokens"] == 128
    assert "temperature" not in fake_http_client.last_json
    assert "Skipping unsupported temperature override" not in caplog.text
    assert content == '{"ok": true}'
    assert usage == {
        "model": "gpt-5-nano-2025-08-07",
        "provider": "openai",
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }


@pytest.mark.asyncio
async def test_openai_adapter_keeps_larger_reasoning_token_budget():
    adapter = OpenAIAdapter(
        "openai",
        {
            "model": "gpt-5-nano-2025-08-07",
            "api_base": "https://api.openai.com/v1",
        },
    )
    adapter.api_key = "test-key"
    fake_http_client = _FakeAsyncClient()
    adapter._http_client = fake_http_client

    await adapter.call(
        system_prompt="sys",
        user_prompt="user",
        temperature=0.7,
        max_tokens=12000,
    )

    assert fake_http_client.last_json["max_completion_tokens"] == 12000
    assert "temperature" not in fake_http_client.last_json


@pytest.mark.asyncio
async def test_openai_adapter_uses_configured_role_specific_reasoning_controls():
    adapter = OpenAIAdapter(
        "openai_shadow",
        {
            "model": "gpt-5.4-nano",
            "api_base": "https://api.openai.com/v1",
            "reasoning_effort": "low",
            "min_completion_tokens": 384,
        },
    )
    adapter.api_key = "test-key"
    fake_http_client = _FakeAsyncClient()
    adapter._http_client = fake_http_client

    await adapter.call("sys", "user", max_tokens=120)

    assert fake_http_client.last_json["max_completion_tokens"] == 384
    assert fake_http_client.last_json["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_openai_adapter_forwards_strict_json_schema() -> None:
    adapter = OpenAIAdapter(
        "openai_shadow",
        {"model": "gpt-5.4-nano", "api_base": "https://api.openai.com/v1"},
    )
    adapter.api_key = "test-key"
    fake_http_client = _FakeAsyncClient()
    adapter._http_client = fake_http_client
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "activation",
            "strict": True,
            "schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    }

    await adapter.call("sys", "user", response_format=response_format)

    assert fake_http_client.last_json["response_format"] == response_format


@pytest.mark.asyncio
async def test_openai_adapter_keeps_temperature_for_non_reasoning_models():
    adapter = OpenAIAdapter(
        "openai",
        {
            "model": "gpt-4o",
            "api_base": "https://api.openai.com/v1",
        },
    )
    adapter.api_key = "test-key"
    fake_http_client = _FakeAsyncClient()
    adapter._http_client = fake_http_client

    await adapter.call(
        system_prompt="sys",
        user_prompt="user",
        temperature=0.7,
        max_tokens=128,
    )

    assert fake_http_client.last_json["temperature"] == 0.7
