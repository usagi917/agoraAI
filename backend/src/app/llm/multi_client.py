"""MultiLLMClient: エージェントの llm_backend に基づいてアダプタにルーティング"""

import asyncio
import json
import logging
import os
import re
from typing import Optional

from src.app.config import settings
from src.app.llm.adapters.base import LLMAdapter
from src.app.llm.adapters.openai_adapter import OpenAIAdapter
from src.app.llm.adapters.anthropic_adapter import AnthropicAdapter
from src.app.llm.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

ADAPTER_CLASSES = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
}


def _extract_json(text: str) -> Optional[dict]:
    """テキストから JSON を抽出する。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace : last_brace + 1])
        except json.JSONDecodeError:
            pass

    return None


class MultiLLMClient:
    """エージェントの llm_backend に基づいてプロバイダ別アダプタにルーティングする。"""

    def __init__(self):
        self._adapters: dict[str, LLMAdapter] = {}
        self._rate_limiters: dict[str, RateLimiter] = {}
        self._fallback_order: list[str] = []
        self._initialized = False

    def initialize(self) -> None:
        """設定ファイルからアダプタを初期化する。"""
        if self._initialized:
            return

        providers_config = settings.load_llm_providers_config()
        providers = providers_config.get("providers", {})
        self._fallback_order = providers_config.get("fallback_order", [])

        for name, config in providers.items():
            if not config.get("enabled", True):
                continue

            env_key = config.get("env_key", "")
            api_key = os.environ.get(env_key, "") or getattr(settings, env_key.lower(), "")
            if not api_key:
                logger.info("Provider %s skipped: no API key (%s)", name, env_key)
                continue

            adapter_type = config.get("type", "openai")
            adapter_cls = ADAPTER_CLASSES.get(adapter_type, OpenAIAdapter)
            adapter = adapter_cls(name, config)
            adapter.api_key = api_key
            self._adapters[name] = adapter

            rate_cfg = config.get("rate_limit", {})
            self._rate_limiters[name] = RateLimiter(
                rpm=rate_cfg.get("rpm", 500),
                tpm=rate_cfg.get("tpm", 200000),
                max_concurrent=rate_cfg.get("max_concurrent", 20),
            )

        self._initialized = True
        logger.info("MultiLLMClient initialized with providers: %s", list(self._adapters.keys()))

    def available_providers(self) -> list[str]:
        """利用可能なプロバイダ名リストを返す。"""
        self.initialize()
        return list(self._adapters.keys())

    def _resolve_provider(self, provider_name: str) -> tuple[LLMAdapter, RateLimiter]:
        """プロバイダ名からアダプタを解決する。利用不可ならフォールバック。"""
        self.initialize()

        if provider_name in self._adapters:
            return self._adapters[provider_name], self._rate_limiters[provider_name]

        # フォールバック
        for fallback in self._fallback_order:
            if fallback in self._adapters:
                logger.warning("Provider %s unavailable, falling back to %s", provider_name, fallback)
                return self._adapters[fallback], self._rate_limiters[fallback]

        # 最後の手段: 最初の利用可能なアダプタ
        if self._adapters:
            first = next(iter(self._adapters))
            logger.warning("No provider match, using first available: %s", first)
            return self._adapters[first], self._rate_limiters[first]

        raise RuntimeError("No LLM providers available. Check API keys and llm_providers.yaml.")

    async def call(
        self,
        provider_name: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 1024,
    ) -> tuple[dict | str, dict]:
        """指定プロバイダで LLM を呼び出す。"""
        adapter, limiter = self._resolve_provider(provider_name)

        await limiter.acquire(estimated_tokens=max_tokens)
        try:
            content, usage = await adapter.call(
                system_prompt, user_prompt, temperature, max_tokens,
            )
        except Exception as e:
            logger.error("MultiLLM call failed for %s: %s", provider_name, e)
            raise
        finally:
            limiter.release()

        limiter.record_usage(usage.get("total_tokens", 0))

        parsed = _extract_json(content)
        if parsed is not None:
            return parsed, usage
        return content, usage

    async def call_batch_by_provider(
        self,
        calls: list[dict],
        max_concurrency: int = 20,
    ) -> list[tuple[dict | str, dict]]:
        """プロバイダ別にグループ化してバッチ呼び出しを行う。

        calls: list of {
            "provider": str,
            "system_prompt": str,
            "user_prompt": str,
            "temperature": float,
            "max_tokens": int,
        }
        """
        sem = asyncio.Semaphore(max_concurrency)

        async def _single(call_params: dict):
            async with sem:
                return await self.call(
                    provider_name=call_params["provider"],
                    system_prompt=call_params["system_prompt"],
                    user_prompt=call_params["user_prompt"],
                    temperature=call_params.get("temperature", 0.5),
                    max_tokens=call_params.get("max_tokens", 1024),
                )

        results = await asyncio.gather(
            *[_single(c) for c in calls],
            return_exceptions=True,
        )

        processed = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("Batch call failed: %s", r)
                processed.append((
                    "",
                    {"model": "unknown", "provider": "unknown",
                     "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                ))
            else:
                processed.append(r)
        return processed

    async def close(self) -> None:
        """全アダプタを閉じる。"""
        for adapter in self._adapters.values():
            await adapter.close()


multi_llm_client = MultiLLMClient()
