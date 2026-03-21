"""LLM API クライアント: OpenAI / Ollama 対応 + JSON 抽出 + retry"""

import asyncio
import json
import logging
import re
from typing import Any, Callable, Optional

import httpx

from src.app.config import settings
from src.app.llm.rate_limiter import RateLimiter
from src.app.llm.validator import get_task_validator

logger = logging.getLogger(__name__)

REQUIRED_TASKS = {
    "agent_generate",
    "bdi_deliberate",
    "bdi_execute",
    "bdi_perceive",
    "batch_conversation_respond",
    "batch_reactive_process",
    "causal_intervene",
    "claim_extract",
    "community_summary",
    "debate_judge",
    "entity_dedup",
    "entity_extract",
    "final_report",
    "followup",
    "gm_action_resolve",
    "gm_consistency_check",
    "memory_importance",
    "negotiation",
    "pm_board_chief_pm",
    "pm_board_discovery_pm",
    "pm_board_execution_pm",
    "pm_board_strategy_pm",
    "reflection",
    "relation_extract",
    "report_generate",
    "round_process",
    "self_critique",
    "tom_infer",
    "world_build",
}


def _extract_json(text: str) -> Optional[Any]:
    """テキストから JSON を抽出する。thinking タグや markdown コードブロックに対応。"""
    # thinking タグを除去
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()

    # そのまま JSON パース
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ```json ... ``` ブロック抽出
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # { ... } の最初と最後のマッチを探す
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace : last_brace + 1])
        except json.JSONDecodeError:
            pass

    return None


def _merge_usage(usage1: dict, usage2: dict) -> dict:
    """2回分の usage を合算する。"""
    merged = {
        "model": usage1["model"],
        "prompt_tokens": usage1["prompt_tokens"] + usage2["prompt_tokens"],
        "completion_tokens": usage1["completion_tokens"] + usage2["completion_tokens"],
        "total_tokens": usage1["total_tokens"] + usage2["total_tokens"],
    }
    for key in ("retry_count", "validation_failures", "json_retries"):
        merged[key] = int(usage1.get(key, 0) or 0) + int(usage2.get(key, 0) or 0)
    merged["last_validation_error"] = (
        str(usage2.get("last_validation_error") or "")
        or str(usage1.get("last_validation_error") or "")
    )
    return merged


def _annotate_usage(
    usage: dict,
    *,
    retry_count: int = 0,
    validation_failures: int = 0,
    json_retries: int = 0,
    last_validation_error: str = "",
) -> dict:
    annotated = dict(usage)
    annotated["retry_count"] = retry_count
    annotated["validation_failures"] = validation_failures
    annotated["json_retries"] = json_retries
    annotated["last_validation_error"] = last_validation_error
    return annotated


def _validation_error_summary(error: Exception) -> str:
    return f"{type(error).__name__}: {str(error)[:300]}"


class LLMClient:
    def __init__(self):
        self._llm_config = settings.load_model_config()
        self.default_model = self._llm_config.get("default_model", "gpt-5-nano-2025-08-07")
        self.api_base = self._llm_config.get("api_base", "https://api.openai.com/v1")
        self.provider = self._llm_config.get("provider", "openai")
        self.tasks = self._llm_config.get("tasks", {})
        self._http_client: httpx.AsyncClient | None = None

        rate_config = settings.load_rate_limit_config()
        self._rate_limiter = RateLimiter(
            rpm=rate_config.get("rpm", 500),
            tpm=rate_config.get("tpm", 200000),
            max_concurrent=rate_config.get("concurrent_requests", 20),
        )

    def _get_task_config(self, task_name: str) -> dict:
        config = self.tasks.get(task_name)
        if config is None:
            raise ValueError(f"LLM task '{task_name}' is not configured in config/models.yaml")
        return config

    def _get_model_name(self, config: dict) -> str:
        """モデル名を取得（ollama/ プレフィックスがあれば除去）"""
        model = config.get("model", self.default_model)
        return model.removeprefix("ollama/")

    def _is_ollama(self) -> bool:
        return self.provider == "ollama"

    def _uses_reasoning_controls(self, model: str) -> bool:
        return model.startswith("gpt-5") or model.startswith(("o1", "o3", "o4"))

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            timeout = httpx.Timeout(1800.0 if self._is_ollama() else 300.0)
            self._http_client = httpx.AsyncClient(timeout=timeout)
        return self._http_client

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def _call_openai(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
        reasoning_effort: str | None = None,
    ) -> tuple[str, dict]:
        """OpenAI API 互換エンドポイントを呼び出す"""
        url = f"{self.api_base}/chat/completions"

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        if self._uses_reasoning_controls(model):
            if temperature not in (1, 1.0):
                logger.info(
                    "Skipping unsupported temperature override for reasoning model %s: %s",
                    model,
                    temperature,
                )
            if reasoning_effort:
                body["reasoning_effort"] = reasoning_effort
        else:
            body["temperature"] = temperature
        if response_format and response_format.get("type") == "json_object":
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.openai_api_key}",
        }

        client = self._get_http_client()
        resp = await client.post(url, json=body, headers=headers)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error(
                "OpenAI API request failed: status=%s body=%s",
                resp.status_code,
                resp.text[:2000],
            )
            raise
        data = resp.json()

        choice = data["choices"][0]
        content = choice["message"]["content"] or ""
        api_usage = data.get("usage", {})
        usage = {
            "model": model,
            "prompt_tokens": api_usage.get("prompt_tokens", 0),
            "completion_tokens": api_usage.get("completion_tokens", 0),
            "total_tokens": api_usage.get("total_tokens", 0),
        }
        return content, usage

    async def _call_ollama(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
    ) -> tuple[str, dict]:
        """Ollama API を直接呼び出す"""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if response_format and response_format.get("type") == "json_object":
            body["format"] = "json"

        url = f"{self.api_base}/api/chat"
        client = self._get_http_client()
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()

        content = data.get("message", {}).get("content", "")
        usage = {
            "model": model,
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
            "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        }
        return content, usage

    async def call(
        self,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
        response_format: dict | None = None,
    ) -> tuple[dict | str, dict]:
        """LLM API を呼び出して結果を返す。"""
        config = self._get_task_config(task_name)
        model = self._get_model_name(config)
        temperature = config.get("temperature", 0.3)
        max_tokens = config.get("max_tokens", 4096)
        reasoning_effort = config.get("reasoning_effort")

        if self._is_ollama():
            # Qwen 3.5: system + user を統合し、/no_think で thinking を無効化
            combined_prompt = f"/no_think\n{system_prompt}\n\n{user_prompt}"
            messages = [{"role": "user", "content": combined_prompt}]
        else:
            # OpenAI API: system/user メッセージを分離
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

        prompt_len = len(system_prompt) + len(user_prompt)
        logger.info(f"LLM call: task={task_name}, model={model}, prompt_chars={prompt_len}")

        await self._rate_limiter.acquire(estimated_tokens=max_tokens)
        try:
            if self._is_ollama():
                content, usage = await self._call_ollama(
                    model, messages, temperature, max_tokens, response_format
                )
            else:
                content, usage = await self._call_openai(
                    model,
                    messages,
                    temperature,
                    max_tokens,
                    response_format,
                    reasoning_effort=reasoning_effort,
                )
        except Exception as e:
            logger.error(f"LLM call failed for task {task_name}: {e}")
            raise
        finally:
            self._rate_limiter.release()

        self._rate_limiter.record_usage(usage.get("total_tokens", 0))

        logger.info(
            f"LLM response: task={task_name}, tokens={usage['total_tokens']}, len={len(content)}"
        )

        # JSON 抽出
        parsed = _extract_json(content)
        if parsed is not None:
            return parsed, usage

        # JSON 抽出失敗時は文字列として返す
        logger.warning(f"JSON extraction failed for {task_name}, content[:200]={content[:200]}")
        return content, usage

    async def call_with_retry(
        self,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
        response_format: dict | None = None,
        validate_fn: Optional[Callable] = None,
    ) -> tuple[Any, dict]:
        """LLM 呼び出し + validation 失敗時に1回 retry。"""
        effective_validate_fn = validate_fn or get_task_validator(task_name)
        retry_count = 0
        validation_failures = 0
        json_retries = 0
        last_validation_error = ""
        result, usage = await self.call(task_name, system_prompt, user_prompt, response_format)

        # JSON パース失敗の場合はリトライ
        if not isinstance(result, dict):
            retry_count += 1
            json_retries += 1
            logger.warning(
                "LLM JSON retry task=%s reason=non_json_initial_response",
                task_name,
            )
            retry_prompt = (
                f"{user_prompt}\n\n"
                "重要: 有効な JSON のみを出力してください。説明文やマークダウンは不要です。"
            )
            result2, usage2 = await self.call(
                task_name, system_prompt, retry_prompt, response_format
            )
            if isinstance(result2, dict) and effective_validate_fn:
                effective_validate_fn(result2)
            return result2, _annotate_usage(
                _merge_usage(usage, usage2),
                retry_count=retry_count,
                validation_failures=validation_failures,
                json_retries=json_retries,
                last_validation_error=last_validation_error,
            )

        # dict が返ってきた場合にバリデーション
        if effective_validate_fn:
            try:
                effective_validate_fn(result)
                return result, _annotate_usage(
                    usage,
                    retry_count=retry_count,
                    validation_failures=validation_failures,
                    json_retries=json_retries,
                    last_validation_error=last_validation_error,
                )
            except Exception as e:
                retry_count += 1
                validation_failures += 1
                last_validation_error = _validation_error_summary(e)
                logger.warning(
                    "LLM validation retry task=%s error=%s",
                    task_name,
                    last_validation_error,
                )
                retry_prompt = (
                    f"{user_prompt}\n\n"
                    f"前回の出力にバリデーションエラー: {e}\n"
                    "正しい JSON 形式で再出力してください。"
                )
                result2, usage2 = await self.call(
                    task_name, system_prompt, retry_prompt, response_format
                )
                if isinstance(result2, dict) and effective_validate_fn:
                    effective_validate_fn(result2)
                return result2, _annotate_usage(
                    _merge_usage(usage, usage2),
                    retry_count=retry_count,
                    validation_failures=validation_failures,
                    json_retries=json_retries,
                    last_validation_error=last_validation_error,
                )

        return result, _annotate_usage(
            usage,
            retry_count=retry_count,
            validation_failures=validation_failures,
            json_retries=json_retries,
            last_validation_error=last_validation_error,
        )

    async def call_batch(
        self,
        calls: list[dict],
        max_concurrency: int | None = None,
    ) -> list[tuple[dict | str, dict]]:
        """複数LLM呼び出しをSemaphore付きで並列実行する。

        calls: list of {"task_name": str, "system_prompt": str, "user_prompt": str, "response_format": dict | None}
        """
        sem = asyncio.Semaphore(max_concurrency or settings.max_concurrent_agents)

        async def _single(call_params):
            async with sem:
                return await self.call(**call_params)

        results = await asyncio.gather(
            *[_single(c) for c in calls],
            return_exceptions=True,
        )

        processed = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"Batch call failed: {r}")
                processed.append(("", {"model": "unknown", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}))
            else:
                processed.append(r)
        return processed


llm_client = LLMClient()


def validate_task_registry() -> None:
    config = settings.load_model_config()
    tasks = set((config.get("tasks") or {}).keys())
    missing = sorted(REQUIRED_TASKS - tasks)
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing required LLM task configuration(s): {joined}")
