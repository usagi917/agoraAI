"""マルチプロバイダーアンサンブル + 障害ポリシー

2-3 プロバイダーを並列呼出しし、クォーラムベースで結果を集約する。
部分障害: クォーラム(>=2/3)成功で集約、1のみなら信頼度低減で使用。
全失敗: RuntimeError を送出。
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# 共通レスポンススキーマ
_SCHEMA_KEYS = {"stance", "confidence", "reason", "concern"}


def _normalize_response(raw: dict[str, Any]) -> dict[str, Any]:
    """レスポンスを共通スキーマに正規化する."""
    return {k: raw.get(k, "" if k != "confidence" else 0.5) for k in _SCHEMA_KEYS}


async def call_with_ensemble(
    prompt: str,
    providers: list[Callable[[str], Coroutine[Any, Any, dict]]],
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """複数プロバイダーを並列呼出しし、クォーラムベースで集約する.

    Args:
        prompt: LLM に渡すプロンプト
        providers: 各プロバイダーの async 関数リスト
        timeout_seconds: プロバイダーごとのタイムアウト（秒）

    Returns:
        集約された応答 + quorum_size

    Raises:
        RuntimeError: クォーラム不成立（全プロバイダー失敗）
    """
    async def _safe_call(provider):
        try:
            return await asyncio.wait_for(provider(prompt), timeout=timeout_seconds)
        except Exception as exc:
            logger.warning("Provider failed: %s", exc)
            return None

    results = await asyncio.gather(*[_safe_call(p) for p in providers])
    successes = [_normalize_response(r) for r in results if r is not None]
    quorum_size = len(successes)

    if quorum_size == 0:
        raise RuntimeError("Ensemble quorum not met: all providers failed")

    # 多数決でスタンス決定
    stance_counts = Counter(r["stance"] for r in successes)
    majority_stance = stance_counts.most_common(1)[0][0]

    # confidence の平均
    avg_confidence = sum(r["confidence"] for r in successes) / quorum_size

    # 単一プロバイダーのみ成功の場合は信頼度低減
    if quorum_size == 1 and len(providers) > 1:
        avg_confidence *= 0.7

    # reason/concern は最初の成功レスポンスから取得
    first = successes[0]

    return {
        "stance": majority_stance,
        "confidence": round(avg_confidence, 4),
        "reason": first["reason"],
        "concern": first["concern"],
        "quorum_size": quorum_size,
    }
