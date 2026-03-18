"""Token Bucket レート制限 + Semaphore 並列制御"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token Bucket アルゴリズム: RPM/TPM 制御。"""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate          # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, amount: float = 1.0) -> None:
        """指定量のトークンを取得する。不足時は待機。"""
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= amount:
                    self.tokens -= amount
                    return
                wait_time = (amount - self.tokens) / self.rate
            await asyncio.sleep(min(wait_time, 1.0))

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self._last_refill = now


class RateLimiter:
    """RPM + TPM + 並列数制限の統合レート制限。"""

    def __init__(self, rpm: int = 500, tpm: int = 200000, max_concurrent: int = 20):
        self._rpm_bucket = TokenBucket(rate=rpm / 60.0, capacity=rpm)
        self._tpm_bucket = TokenBucket(rate=tpm / 60.0, capacity=tpm)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._total_requests = 0
        self._total_tokens = 0

    async def acquire(self, estimated_tokens: int = 1000) -> None:
        """リクエスト発行前にレート制限を適用する。"""
        await self._rpm_bucket.acquire(1.0)
        await self._tpm_bucket.acquire(float(estimated_tokens))
        await self._semaphore.acquire()

    def release(self) -> None:
        """リクエスト完了後にセマフォを解放する。"""
        self._semaphore.release()

    def record_usage(self, tokens: int) -> None:
        """実際のトークン使用量を記録する。"""
        self._total_requests += 1
        self._total_tokens += tokens

    @property
    def stats(self) -> dict:
        return {
            "total_requests": self._total_requests,
            "total_tokens": self._total_tokens,
        }
