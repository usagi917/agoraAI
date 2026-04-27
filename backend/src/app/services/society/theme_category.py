"""theme_category 推定結果の型定義と共有定数"""

from __future__ import annotations

from dataclasses import dataclass

# MVP として精度保証対象のカテゴリ
MVP_CATEGORIES: frozenset[str] = frozenset({"economy", "security"})

# アンカリングを許可する最低 confidence 閾値（MVP カテゴリのみ適用）
ANCHOR_MIN_CONFIDENCE: float = 0.4

# キーワード 1 件あたりの confidence 寄与
CONFIDENCE_PER_KEYWORD: float = 0.2


@dataclass
class ThemeCategoryEstimate:
    """テーマカテゴリ推定結果。

    Attributes:
        category: 推定カテゴリ名。マッチなし時は "unknown"。
        confidence: 推定の確信度 (0.0–1.0)。
        source: 推定の根拠。"override" | "grounding_facts" | "keyword_match" | "fallback"
        is_anchor_eligible: このカテゴリで survey アンカリングを行ってよいか。
    """

    category: str
    confidence: float
    source: str
    is_anchor_eligible: bool
