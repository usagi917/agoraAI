"""プライバシーポリシー: PII リダクション・同意管理・保持期限

インタビューグラウンディングのパイプラインに適用する。
"""

from __future__ import annotations

import re

# データ保持期限（日数）
RETENTION_DAYS = 90

# PII パターン
_PHONE_PATTERN = re.compile(r"\d{2,4}[-\s]?\d{2,4}[-\s]?\d{3,4}")
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_NAME_PATTERN = re.compile(r"[一-龥ぁ-んァ-ヶ]{2,4}(?:太郎|花子|一郎|次郎|三郎|子|美|恵)")


def redact_pii(text: str) -> str:
    """テキストから PII（電話番号・メール・氏名パターン）をリダクトする."""
    text = _PHONE_PATTERN.sub("[REDACTED_PHONE]", text)
    text = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    text = _NAME_PATTERN.sub("[REDACTED_NAME]", text)
    return text


class ConsentManager:
    """ユーザー同意の管理."""

    def __init__(self) -> None:
        self._consents: set[str] = set()

    def grant_consent(self, user_id: str) -> None:
        self._consents.add(user_id)

    def revoke_consent(self, user_id: str) -> None:
        self._consents.discard(user_id)

    def has_consent(self, user_id: str) -> bool:
        return user_id in self._consents
