"""LLMAdapter 抽象基底クラス"""

from abc import ABC, abstractmethod


class LLMAdapter(ABC):
    """マルチプロバイダ LLM アダプタの抽象基底クラス。"""

    def __init__(self, provider_name: str, config: dict):
        self.provider_name = provider_name
        self.model = config.get("model", "")
        self.api_base = config.get("api_base", "")
        self.api_key: str = ""  # 初期化時に設定される

    @abstractmethod
    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 1024,
        seed: int | None = None,
    ) -> tuple[str, dict]:
        """LLM を呼び出し、(content, usage) を返す。

        usage: {"model": str, "prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        """

    @abstractmethod
    async def close(self) -> None:
        """HTTP クライアントを閉じる。"""
