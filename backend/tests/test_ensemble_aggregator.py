"""P2-3: マルチプロバイダーアンサンブルのテスト"""

import pytest


class TestEnsembleAggregator:
    """ensemble_aggregator.py のテスト."""

    @pytest.mark.asyncio
    async def test_full_quorum(self):
        """全プロバイダー成功時の集約."""
        from src.app.services.society.ensemble_aggregator import call_with_ensemble

        async def mock_provider_a(prompt):
            return {"stance": "賛成", "confidence": 0.8, "reason": "理由A", "concern": "懸念A"}

        async def mock_provider_b(prompt):
            return {"stance": "賛成", "confidence": 0.7, "reason": "理由B", "concern": "懸念B"}

        result = await call_with_ensemble(
            prompt="test", providers=[mock_provider_a, mock_provider_b],
        )
        assert result["stance"] == "賛成"
        assert result["confidence"] > 0.0
        assert result["quorum_size"] == 2

    @pytest.mark.asyncio
    async def test_partial_failure_quorum(self):
        """1プロバイダー失敗でもクォーラム (>=2/3) 達成なら成功."""
        from src.app.services.society.ensemble_aggregator import call_with_ensemble

        async def good_a(prompt):
            return {"stance": "反対", "confidence": 0.9, "reason": "R", "concern": "C"}

        async def good_b(prompt):
            return {"stance": "反対", "confidence": 0.7, "reason": "R", "concern": "C"}

        async def bad(prompt):
            raise TimeoutError("provider timeout")

        result = await call_with_ensemble(
            prompt="test", providers=[good_a, good_b, bad],
        )
        assert result["stance"] == "反対"
        assert result["quorum_size"] == 2

    @pytest.mark.asyncio
    async def test_single_provider_reduced_confidence(self):
        """1プロバイダーのみ成功時は信頼度低減."""
        from src.app.services.society.ensemble_aggregator import call_with_ensemble

        async def good(prompt):
            return {"stance": "賛成", "confidence": 0.9, "reason": "R", "concern": "C"}

        async def bad_1(prompt):
            raise Exception("fail")

        async def bad_2(prompt):
            raise Exception("fail")

        result = await call_with_ensemble(
            prompt="test", providers=[good, bad_1, bad_2],
        )
        assert result["stance"] == "賛成"
        assert result["confidence"] < 0.9  # 信頼度が低減されている
        assert result["quorum_size"] == 1

    @pytest.mark.asyncio
    async def test_all_fail_raises(self):
        """全プロバイダー失敗時は例外."""
        from src.app.services.society.ensemble_aggregator import call_with_ensemble

        async def bad(prompt):
            raise Exception("fail")

        with pytest.raises(RuntimeError, match="quorum"):
            await call_with_ensemble(prompt="test", providers=[bad, bad])

    @pytest.mark.asyncio
    async def test_schema_normalization(self):
        """異なるレスポンス形式が共通スキーマに正規化されること."""
        from src.app.services.society.ensemble_aggregator import call_with_ensemble

        async def provider_with_extras(prompt):
            return {
                "stance": "中立",
                "confidence": 0.5,
                "reason": "理由",
                "concern": "懸念",
                "extra_field": "ignored",
            }

        result = await call_with_ensemble(
            prompt="test", providers=[provider_with_extras],
        )
        assert "extra_field" not in result
        assert "stance" in result
        assert "confidence" in result
        assert "reason" in result
        assert "concern" in result
