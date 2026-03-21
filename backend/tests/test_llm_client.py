import pytest

from src.app.config import Settings, settings
from src.app.llm.client import LLMClient, validate_task_registry


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
async def test_call_openai_uses_max_completion_tokens(monkeypatch: pytest.MonkeyPatch):
    client = LLMClient()
    fake_http_client = _FakeAsyncClient()
    client._http_client = fake_http_client

    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    content, usage = await client._call_openai(
        model="gpt-5-nano-2025-08-07",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.3,
        max_tokens=128,
        response_format={"type": "json_object"},
        reasoning_effort="minimal",
    )

    assert fake_http_client.last_url.endswith("/chat/completions")
    assert fake_http_client.last_json["max_completion_tokens"] == 128
    assert "max_tokens" not in fake_http_client.last_json
    assert "temperature" not in fake_http_client.last_json
    assert fake_http_client.last_json["reasoning_effort"] == "minimal"
    assert fake_http_client.last_json["response_format"] == {"type": "json_object"}
    assert content == '{"ok": true}'
    assert usage == {
        "model": "gpt-5-nano-2025-08-07",
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }


def test_get_task_config_raises_for_missing_task():
    client = LLMClient()

    with pytest.raises(ValueError, match="not configured"):
        client._get_task_config("missing_task")


def test_validate_task_registry_raises_for_missing_required_task(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        Settings,
        "load_model_config",
        lambda self: {"tasks": {"world_build": {}}},
    )

    with pytest.raises(RuntimeError, match="Missing required LLM task configuration"):
        validate_task_registry()


@pytest.mark.asyncio
async def test_call_with_retry_tracks_validation_failures(monkeypatch: pytest.MonkeyPatch):
    client = LLMClient()
    calls = [
        ({"bad": True}, {"model": "gpt-4o", "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}),
        ({"ok": True}, {"model": "gpt-4o", "prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12}),
    ]

    async def _fake_call(*args, **kwargs):
        return calls.pop(0)

    monkeypatch.setattr(client, "call", _fake_call)

    def _validate(payload: dict):
        if "ok" not in payload:
            raise ValueError("missing ok")

    result, usage = await client.call_with_retry(
        task_name="world_build",
        system_prompt="sys",
        user_prompt="user",
        response_format={"type": "json_object"},
        validate_fn=_validate,
    )

    assert result == {"ok": True}
    assert usage["retry_count"] == 1
    assert usage["validation_failures"] == 1
    assert usage["json_retries"] == 0
    assert "ValueError" in usage["last_validation_error"]
