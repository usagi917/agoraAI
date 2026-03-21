"""Anthropic Messages API 用アダプタ"""

import logging

import httpx

from src.app.llm.adapters.base import LLMAdapter

logger = logging.getLogger(__name__)


class AnthropicAdapter(LLMAdapter):
    """Anthropic Messages API アダプタ。"""

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
        return self._http_client

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 1024,
    ) -> tuple[str, dict]:
        url = f"{self.api_base}/v1/messages"

        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        client = self._get_http_client()
        resp = await client.post(url, json=body, headers=headers)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error(
                "Anthropic adapter request failed: status=%s body=%s",
                resp.status_code, resp.text[:500],
            )
            raise

        data = resp.json()
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        api_usage = data.get("usage", {})
        usage = {
            "model": self.model,
            "provider": self.provider_name,
            "prompt_tokens": api_usage.get("input_tokens", 0),
            "completion_tokens": api_usage.get("output_tokens", 0),
            "total_tokens": api_usage.get("input_tokens", 0) + api_usage.get("output_tokens", 0),
        }
        return content, usage

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
