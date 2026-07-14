"""Native Ollama adapter tests for the Liquid population model."""

import pytest

from src.app.llm.adapters.ollama_adapter import OllamaAdapter


class _FakeResponse:
    status_code = 200
    text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "message": {"content": '{"stance":"賛成","confidence":0.7}'},
            "prompt_eval_count": 31,
            "eval_count": 17,
        }


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.is_closed = False
        self.last_url = ""
        self.last_json: dict = {}
        self.last_headers: dict | None = None

    async def post(self, url: str, json: dict, headers: dict | None = None):
        self.last_url = url
        self.last_json = json
        self.last_headers = headers
        return _FakeResponse()

    async def get(self, url: str):
        self.last_url = url
        return _FakeTagsResponse([
            "hf.co/LiquidAI/LFM2.5-1.2B-JP-202606-GGUF:Q8_0",
        ])


class _FakeTagsResponse(_FakeResponse):
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def json(self) -> dict:
        return {"models": [{"name": name} for name in self._names]}


@pytest.mark.asyncio
async def test_ollama_adapter_uses_native_chat_and_json_schema() -> None:
    adapter = OllamaAdapter(
        "liquid",
        {
            "model": "hf.co/LiquidAI/LFM2.5-1.2B-JP-202606-GGUF:Q8_0",
            "api_base": "http://127.0.0.1:11434",
            "keep_alive": "30m",
        },
    )
    client = _FakeAsyncClient()
    adapter._http_client = client
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "activation",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"stance": {"type": "string"}},
                "required": ["stance"],
                "additionalProperties": False,
            },
        },
    }

    content, usage = await adapter.call(
        system_prompt="system",
        user_prompt="user",
        temperature=0.3,
        max_tokens=160,
        seed=42,
        response_format=response_format,
    )

    assert client.last_url == "http://127.0.0.1:11434/api/chat"
    assert client.last_headers is None
    assert client.last_json["stream"] is False
    assert client.last_json["format"] == response_format["json_schema"]["schema"]
    assert client.last_json["options"] == {
        "temperature": 0.3,
        "num_predict": 160,
        "seed": 42,
    }
    assert client.last_json["keep_alive"] == "30m"
    assert content.startswith("{")
    assert usage == {
        "model": "hf.co/LiquidAI/LFM2.5-1.2B-JP-202606-GGUF:Q8_0",
        "provider": "liquid",
        "prompt_tokens": 31,
        "completion_tokens": 17,
        "total_tokens": 48,
    }


@pytest.mark.asyncio
async def test_ollama_adapter_maps_json_object_to_json_format() -> None:
    adapter = OllamaAdapter("liquid", {"model": "lfm", "api_base": "http://localhost:11434"})
    client = _FakeAsyncClient()
    adapter._http_client = client

    await adapter.call("system", "user", response_format={"type": "json_object"})

    assert client.last_json["format"] == "json"


@pytest.mark.asyncio
async def test_ollama_adapter_preflight_confirms_exact_model() -> None:
    adapter = OllamaAdapter(
        "liquid",
        {
            "model": "hf.co/LiquidAI/LFM2.5-1.2B-JP-202606-GGUF:Q8_0",
            "api_base": "http://localhost:11434",
        },
    )
    client = _FakeAsyncClient()
    adapter._http_client = client

    await adapter.ensure_ready()

    assert client.last_url == "http://localhost:11434/api/tags"


@pytest.mark.asyncio
async def test_ollama_adapter_preflight_fails_before_population_loop() -> None:
    adapter = OllamaAdapter(
        "liquid",
        {"model": "missing-model", "api_base": "http://localhost:11434"},
    )
    client = _FakeAsyncClient()

    async def missing_get(url: str):
        client.last_url = url
        return _FakeTagsResponse([])

    client.get = missing_get
    adapter._http_client = client

    with pytest.raises(RuntimeError, match="missing-model"):
        await adapter.ensure_ready()
