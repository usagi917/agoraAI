"""コスト/レイテンシ監視

フェーズ別タイミング計測、LLMトークン使用量追跡、予算超過で中断。
"""

from __future__ import annotations

import time


class CostMonitor:
    """トークン予算管理とフェーズ別タイミング計測."""

    def __init__(self, budget_tokens: int) -> None:
        self._budget = budget_tokens
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._phase_starts: dict[str, float] = {}
        self.phase_timings: dict[str, float] = {}

    def record_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self._prompt_tokens += prompt_tokens
        self._completion_tokens += completion_tokens

    @property
    def total_tokens(self) -> int:
        return self._prompt_tokens + self._completion_tokens

    @property
    def remaining_budget(self) -> int:
        return max(0, self._budget - self.total_tokens)

    def is_budget_exceeded(self) -> bool:
        return self.total_tokens > self._budget

    def start_phase(self, phase: str) -> None:
        self._phase_starts[phase] = time.monotonic()

    def end_phase(self, phase: str) -> None:
        start = self._phase_starts.pop(phase, None)
        if start is not None:
            self.phase_timings[phase] = time.monotonic() - start

    def get_summary(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "remaining_budget": self.remaining_budget,
            "budget_exceeded": self.is_budget_exceeded(),
            "phase_timings": dict(self.phase_timings),
        }
