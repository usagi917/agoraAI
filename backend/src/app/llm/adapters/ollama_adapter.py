"""Native Ollama adapter used by the local Liquid population model."""

import logging
from typing import Any

import httpx

from src.app.llm.adapters.base import LLMAdapter

logger = logging.getLogger(__name__)


class OllamaAdapter(LLMAdapter):
    """Call Ollama's native chat endpoint without an API key."""

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self.keep_alive = config.get("keep_alive", "30m")
        self.timeout_seconds = float(config.get("timeout_seconds", 1800))
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds))
        return self._http_client

    async def ensure_ready(self) -> None:
        """Fail fast unless Ollama is reachable and the configured model exists."""
        url = f"{self.api_base.rstrip('/')}/api/tags"
        try:
            response = await self._get_http_client().get(url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Ollama is unavailable at {self.api_base}; cannot use model {self.model}"
            ) from exc

        available_models = {
            str(item.get("name") or item.get("model") or "")
            for item in payload.get("models", [])
            if isinstance(item, dict)
        }
        if self.model not in available_models:
            raise RuntimeError(
                f"Ollama model {self.model} is not installed; pull it before activation"
            )

    @staticmethod
    def _ollama_format(response_format: dict | None) -> str | dict | None:
        if not response_format:
            return None
        if response_format.get("type") == "json_object":
            return "json"
        if response_format.get("type") == "json_schema":
            json_schema = response_format.get("json_schema") or {}
            schema = json_schema.get("schema")
            return schema if isinstance(schema, dict) else "json"
        return None

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 1024,
        seed: int | None = None,
        response_format: dict | None = None,
    ) -> tuple[str, dict]:
        options: dict[str, Any] = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
        if seed is not None:
            options["seed"] = seed

        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": options,
            "keep_alive": self.keep_alive,
        }
        output_format = self._ollama_format(response_format)
        if output_format is not None:
            body["format"] = output_format

        url = f"{self.api_base.rstrip('/')}/api/chat"
        response = await self._get_http_client().post(url, json=body)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error(
                "Ollama adapter %s request failed: status=%s body=%s",
                self.provider_name,
                response.status_code,
                response.text[:500],
            )
            raise

        data = response.json()
        prompt_tokens = int(data.get("prompt_eval_count", 0) or 0)
        completion_tokens = int(data.get("eval_count", 0) or 0)
        return str(data.get("message", {}).get("content", "") or ""), {
            "model": self.model,
            "provider": self.provider_name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
