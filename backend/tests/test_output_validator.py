"""output_validator.py のテスト — TDD RED フェーズ"""

import pytest

from src.app.services.society.output_validator import (
    classify_response_quality,
    validate_activation_meeting_consistency,
    validate_minority_preservation,
    validate_response_quality,
)

# ---------------------------------------------------------------------------
# テストデータ
# ---------------------------------------------------------------------------

aggregation_oppose_majority = {
    "stance_distribution": {
        "賛成": 0.15,
        "反対": 0.70,
        "中立": 0.05,
        "条件付き賛成": 0.05,
        "条件付き反対": 0.05,
    },
}

aggregation_support_majority = {
    "stance_distribution": {
        "賛成": 0.45,
        "反対": 0.10,
        "中立": 0.10,
        "条件付き賛成": 0.15,
        "条件付き反対": 0.10,
        # 条件付き賛成含め 0.60 が賛成系
    },
}

synthesis_go = {
    "recommendations": ["この政策を推進すべき", "早期導入を推奨"],
    "overall_assessment": "全体として肯定的な評価",
}

synthesis_nogo = {
    "recommendations": ["この政策は見送るべき", "導入を中止すべき"],
    "overall_assessment": "全体として否定的な評価",
}

synthesis_positive = {
    "recommendations": ["政策を推進すべき"],
    "overall_assessment": "賛成意見が多数を占める",
}

# ---------------------------------------------------------------------------
# validate_activation_meeting_consistency
# ---------------------------------------------------------------------------


class TestConsistency:
    def test_consistency_detects_representation_gap(self):
        """70%反対なのに Go推奨 synthesis → representation_gap 警告"""
        result = validate_activation_meeting_consistency(
            aggregation_oppose_majority, synthesis_go
        )
        assert result["status"] == "warning"
        assert result["type"] == "representation_gap"
        assert "detail" in result

    def test_consistency_passes_when_aligned(self):
        """60%賛成で synthesis も肯定的推奨 → OK"""
        result = validate_activation_meeting_consistency(
            aggregation_support_majority, synthesis_positive
        )
        assert result["status"] == "ok"

    def test_consistency_detects_gap_when_support_majority_but_nogo(self):
        """賛成多数なのに No-Go synthesis → representation_gap 警告"""
        result = validate_activation_meeting_consistency(
            aggregation_support_majority, synthesis_nogo
        )
        assert result["status"] == "warning"
        assert result["type"] == "representation_gap"

    def test_consistency_with_neutral_majority_passes(self):
        """中立が多数 → ポジティブ synthesis でも警告なし（多数派が中立なので矛盾なし）"""
        agg = {
            "stance_distribution": {
                "賛成": 0.20,
                "反対": 0.20,
                "中立": 0.60,
            }
        }
        result = validate_activation_meeting_consistency(agg, synthesis_go)
        assert result["status"] == "ok"

    def test_consistency_empty_synthesis_recommendations(self):
        """recommendations が空でも内部エラーを起こさない"""
        empty_synthesis = {"recommendations": [], "overall_assessment": ""}
        result = validate_activation_meeting_consistency(
            aggregation_oppose_majority, empty_synthesis
        )
        # recommendations が空で assessment も空 → 方向性不明 → ok (警告できない)
        assert result["status"] in ("ok", "warning")

    def test_consistency_missing_stance_distribution(self):
        """stance_distribution が欠落しても例外を起こさない"""
        result = validate_activation_meeting_consistency({}, synthesis_go)
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# validate_response_quality
# ---------------------------------------------------------------------------


class TestResponseQuality:
    def _short_response(self):
        return {
            "stance": "賛成",
            "confidence": 0.8,
            "reason": "良いと思います。",  # 短い
        }

    def _default_response(self):
        return {
            "stance": "中立",
            "confidence": 0.5,
            "reason": "特に意見はありません。",
        }

    def _good_response(self):
        return {
            "stance": "反対",
            "confidence": 0.85,
            "reason": (
                "私の職場では2023年以降、この政策の影響を直接受けてきました。"
                "東京都内の中小企業に勤める者として、具体的なコストは月額30万円程度増加しており、"
                "現場の声を無視した推進には強く反対します。"
                "地域の経済状況を鑑みると、慎重な議論が必要です。"
            ),
        }

    def test_response_quality_detects_short_reason(self):
        """reason が100文字未満 → response_quality_rate < 1.0"""
        responses = [self._short_response()]
        result = validate_response_quality(responses)
        assert result["response_quality_rate"] < 1.0
        assert result["low_quality_count"] >= 1
        assert result["total"] == 1
        assert isinstance(result["issues"], list)

    def test_response_quality_detects_default_pattern(self):
        """stance='中立' and confidence=0.5 → 低品質として検出"""
        responses = [self._default_response()]
        result = validate_response_quality(responses)
        assert result["response_quality_rate"] < 1.0
        assert result["low_quality_count"] >= 1

    def test_response_quality_accepts_good_response(self):
        """200文字以上で数字・地名・個人的言及含む → 高品質"""
        responses = [self._good_response()]
        result = validate_response_quality(responses)
        assert result["response_quality_rate"] == 1.0
        assert result["low_quality_count"] == 0

    def test_response_quality_mixed_responses(self):
        """良い1件 + 悪い2件 → rate = 1/3"""
        responses = [
            self._good_response(),
            self._short_response(),
            self._default_response(),
        ]
        result = validate_response_quality(responses)
        assert result["total"] == 3
        assert result["low_quality_count"] == 2
        assert abs(result["response_quality_rate"] - 1 / 3) < 0.01

    def test_response_quality_empty_list(self):
        """空リスト → total=0, rate=1.0 (問題なし)"""
        result = validate_response_quality([])
        assert result["total"] == 0
        assert result["response_quality_rate"] == 1.0
        assert result["low_quality_count"] == 0

    def test_response_quality_missing_reason_key(self):
        """reason キーが欠落 → 低品質扱い、例外なし"""
        responses = [{"stance": "賛成", "confidence": 0.9}]
        result = validate_response_quality(responses)
        assert result["response_quality_rate"] < 1.0

    def test_response_quality_returns_required_keys(self):
        """返り値に必須キーが全て含まれる"""
        result = validate_response_quality([self._good_response()])
        assert "response_quality_rate" in result
        assert "low_quality_count" in result
        assert "total" in result
        assert "issues" in result


# ---------------------------------------------------------------------------
# validate_minority_preservation
# ---------------------------------------------------------------------------


class TestMinorityPreservation:
    def _aggregation_with_minority(self):
        """'条件付き反対' が10% (< 15%) → 少数派"""
        return {
            "stance_distribution": {
                "賛成": 0.50,
                "反対": 0.25,
                "中立": 0.10,
                "条件付き賛成": 0.05,
                "条件付き反対": 0.10,
            }
        }

    def _narrative_without_mention(self):
        return {
            "controversy_areas": [
                {"point": "経済的な懸念がある", "supporting_stances": ["反対"]},
                {"point": "環境問題への配慮が必要", "supporting_stances": ["条件付き賛成"]},
            ]
        }

    def _narrative_with_mention(self):
        return {
            "controversy_areas": [
                {"point": "経済的な懸念がある", "supporting_stances": ["反対"]},
                {
                    "point": "条件付き反対派の懸念: 段階的導入が必要",
                    "supporting_stances": ["条件付き反対"],
                },
                {
                    "point": "条件付き賛成派の懸念: 一定条件のもとで賛成",
                    "supporting_stances": ["条件付き賛成"],
                },
            ]
        }

    def test_minority_preservation_detects_missing(self):
        """'条件付き反対' が10%あるのに narrative に言及なし → 警告"""
        result = validate_minority_preservation(
            self._aggregation_with_minority(), self._narrative_without_mention()
        )
        assert result["status"] == "warning"
        assert "条件付き反対" in result["missing_minorities"]

    def test_minority_preservation_passes_when_included(self):
        """少数派が controversy_areas に含まれる → OK"""
        result = validate_minority_preservation(
            self._aggregation_with_minority(), self._narrative_with_mention()
        )
        assert result["status"] == "ok"
        assert result["missing_minorities"] == []

    def test_minority_preservation_no_minorities(self):
        """全スタンスが15%以上 → 少数派なし → OK"""
        agg = {
            "stance_distribution": {
                "賛成": 0.40,
                "反対": 0.30,
                "中立": 0.30,
            }
        }
        result = validate_minority_preservation(agg, self._narrative_without_mention())
        assert result["status"] == "ok"
        assert result["missing_minorities"] == []

    def test_minority_preservation_empty_controversy_areas(self):
        """controversy_areas が空 → 少数派があれば警告"""
        narrative = {"controversy_areas": []}
        result = validate_minority_preservation(
            self._aggregation_with_minority(), narrative
        )
        assert result["status"] == "warning"

    def test_minority_preservation_missing_controversy_areas_key(self):
        """narrative に controversy_areas キーなし → 例外なし"""
        result = validate_minority_preservation(self._aggregation_with_minority(), {})
        assert result["status"] == "warning"

    def test_minority_preservation_returns_required_keys(self):
        """返り値に status と missing_minorities が含まれる"""
        result = validate_minority_preservation(
            self._aggregation_with_minority(), self._narrative_with_mention()
        )
        assert "status" in result
        assert "missing_minorities" in result


# ---------------------------------------------------------------------------
# Phase B: classify_response_quality (3段階品質分類)
# ---------------------------------------------------------------------------


class TestClassifyResponseQuality:
    """Phase B: レスポンス品質を high/medium/low の3段階に分類するテスト。"""

    def test_high_quality(self):
        """長さ十分 + 具体性あり + 非デフォルト → 'high'"""
        response = {
            "stance": "反対",
            "confidence": 0.85,
            "reason": (
                "私の職場では2023年以降、この政策の影響を直接受けてきました。"
                "東京都内の中小企業に勤める者として、具体的なコストは月額30万円程度増加しており、"
                "現場の声を無視した推進には強く反対します。地域の経済状況を鑑みると、慎重な議論が必要だと痛感しています。"
            ),
        }
        tier = classify_response_quality(response)
        assert tier == "high"

    def test_low_quality_short_reason(self):
        """reason が短すぎる → 'low'"""
        response = {
            "stance": "賛成",
            "confidence": 0.8,
            "reason": "良いと思います。",
        }
        tier = classify_response_quality(response)
        assert tier == "low"

    def test_low_quality_default_pattern(self):
        """stance=中立 + confidence=0.5 → 'low' (デフォルトパターン)"""
        response = {
            "stance": "中立",
            "confidence": 0.5,
            "reason": "特に意見はありませんが、社会にとっては重要な問題であると考えます。何か具体的な影響が見えてくれば、改めて考えたいと思います。慎重に見守りたいです。",
        }
        tier = classify_response_quality(response)
        assert tier == "low"

    def test_medium_quality_no_specificity(self):
        """長さOKだが具体性（数字・地名・個人言及）なし → 'medium'"""
        response = {
            "stance": "賛成",
            "confidence": 0.7,
            "reason": (
                "この政策は社会全体にとって有益であると考えます。"
                "経済的な影響も大きく、今後の展開に期待しています。"
                "国民全体が恩恵を受ける可能性があり、慎重かつ前向きな議論が求められます。"
                "将来の世代にとっても重要な意味を持つでしょう。早期の実現を望みます。"
            ),
        }
        tier = classify_response_quality(response)
        assert tier == "medium"

    def test_medium_quality_exact_default_confidence(self):
        """長さ・具体性OKだが confidence=0.5 ちょうど → 'medium'"""
        response = {
            "stance": "賛成",
            "confidence": 0.5,
            "reason": (
                "私の職場の近くの東京都内では、この政策の影響で月額20万円のコスト増があると聞きました。"
                "しかし一方で長期的な経済効果も見込まれるため、慎重に判断したいと思います。"
                "今後の具体的なデータが出てくるまでは様子を見るのが賢明だと考えています。"
            ),
        }
        tier = classify_response_quality(response)
        assert tier == "medium"

    def test_missing_reason_key(self):
        """reason キーが欠落 → 'low'"""
        response = {"stance": "賛成", "confidence": 0.9}
        tier = classify_response_quality(response)
        assert tier == "low"

    def test_failed_response(self):
        """_failed フラグ付き → 'low'"""
        response = {"stance": "", "confidence": 0.0, "reason": "", "_failed": True}
        tier = classify_response_quality(response)
        assert tier == "low"
