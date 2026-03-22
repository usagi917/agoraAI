"""OpenAI / Gemini 互換エンドポイント用アダプタ"""

import logging

import httpx

from src.app.llm.adapters.base import LLMAdapter

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMAdapter):
    """OpenAI Chat Completions API 互換アダプタ。Gemini の OpenAI 互換エンドポイントにも対応。"""

    def __init__(self, provider_name: str, config: dict):
        super().__init__(provider_name, config)
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
        return self._http_client

    def _uses_reasoning_controls(self) -> bool:
        return self.model.startswith("gpt-5") or self.model.startswith(("o1", "o3", "o4"))

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 1024,
    ) -> tuple[str, dict]:
        url = f"{self.api_base}/chat/completions"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        body: dict = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        if self._uses_reasoning_controls():
            if temperature not in (1, 1.0):
                logger.info(
                    "Skipping unsupported temperature override for reasoning model %s: %s",
                    self.model,
                    temperature,
                )
        else:
            body["temperature"] = temperature

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        client = self._get_http_client()
        resp = await client.post(url, json=body, headers=headers)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error(
                "OpenAI adapter %s request failed: status=%s body=%s",
                self.provider_name, resp.status_code, resp.text[:500],
            )
            raise

        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"]["content"] or ""
        api_usage = data.get("usage", {})
        usage = {
            "model": self.model,
            "provider": self.provider_name,
            "prompt_tokens": api_usage.get("prompt_tokens", 0),
            "completion_tokens": api_usage.get("completion_tokens", 0),
            "total_tokens": api_usage.get("total_tokens", 0),
        }
        return content, usage

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
