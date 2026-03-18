import pytest

from src.app.llm.client import LLMClient


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

    monkeypatch.setattr("src.app.llm.client.settings.openai_api_key", "test-key")

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
