"""P4-2: プライバシーポリシーのテスト"""

import pytest


class TestPrivacyPolicy:
    """PII リダクション・同意管理のテスト."""

    def test_redact_pii(self):
        """PII（電話番号・メールアドレス）がリダクトされること."""
        from src.app.services.society.privacy_policy import redact_pii

        text = "田中太郎（090-1234-5678）taro@example.com に連絡ください。"
        redacted = redact_pii(text)

        assert "090-1234-5678" not in redacted
        assert "taro@example.com" not in redacted
        assert "田中太郎" not in redacted or "[REDACTED]" in redacted

    def test_redact_preserves_non_pii(self):
        """PII でないテキストは保持されること."""
        from src.app.services.society.privacy_policy import redact_pii

        text = "経済政策について議論します。"
        redacted = redact_pii(text)
        assert redacted == text

    def test_consent_check(self):
        """同意チェックが機能すること."""
        from src.app.services.society.privacy_policy import ConsentManager

        mgr = ConsentManager()
        assert mgr.has_consent("user-1") is False

        mgr.grant_consent("user-1")
        assert mgr.has_consent("user-1") is True

        mgr.revoke_consent("user-1")
        assert mgr.has_consent("user-1") is False

    def test_retention_policy(self):
        """保持期限が定義されていること."""
        from src.app.services.society.privacy_policy import RETENTION_DAYS

        assert RETENTION_DAYS > 0
        assert RETENTION_DAYS <= 365
