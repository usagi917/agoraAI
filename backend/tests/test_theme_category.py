"""Step 3: theme_category 推定の堅牢化 — TDD ユニットテスト

RED phase: _estimate_theme_category() と compare_with_surveys() の
新しい振る舞いを先に記述する。実装前はすべて失敗することを確認済み。
"""

from __future__ import annotations

import pytest
import yaml

from src.app.services.society.society_orchestrator import _estimate_theme_category
from src.app.services.society.theme_category import ThemeCategoryEstimate
from src.app.services.society.survey_anchor import compare_with_surveys


# ---------------------------------------------------------------------------
# _estimate_theme_category() のテスト
# ---------------------------------------------------------------------------


class TestEstimateThemeCategory:
    """_estimate_theme_category() の振る舞いテスト"""

    # ------------------------------------------------------------------
    # Task: キーワード 2 件以上ヒット → 正しいカテゴリ + confidence ≥ 0.4
    # ------------------------------------------------------------------
    def test_two_keyword_hits_returns_correct_category(self):
        """economy キーワード("賃金", "景気")が 2 件ヒット → economy + confidence ≥ 0.4"""
        theme = "賃金上昇と景気回復を目指す政策"
        result = _estimate_theme_category(theme)
        assert isinstance(result, ThemeCategoryEstimate)
        assert result.category == "economy"
        assert result.confidence >= 0.4

    # ------------------------------------------------------------------
    # Task: キーワード 0 件ヒット → category="unknown", confidence=0.0
    # ------------------------------------------------------------------
    def test_zero_keyword_hits_returns_unknown(self):
        """どのカテゴリにも一致しない場合 → unknown + confidence=0.0"""
        theme = "xxxxxxxx全く無関係なテーマyyyyyyy"
        result = _estimate_theme_category(theme)
        assert result.category == "unknown"
        assert result.confidence == 0.0
        assert result.is_anchor_eligible is False

    # ------------------------------------------------------------------
    # Task: override 指定時 → 最優先 + confidence=1.0
    # ------------------------------------------------------------------
    def test_override_beats_keyword_match(self):
        """security キーワードを含むテーマでも override="economy" なら economy + confidence=1.0"""
        theme = "防衛費の大幅拡大"
        result = _estimate_theme_category(theme, override="economy")
        assert result.category == "economy"
        assert result.confidence == 1.0
        assert result.source == "override"
        assert result.is_anchor_eligible is True

    def test_override_beats_grounding_facts(self):
        """override は grounding_facts よりも優先される"""
        theme = "防衛予算"
        grounding_facts = [{"theme_category": "security"}]
        result = _estimate_theme_category(theme, override="economy", grounding_facts=grounding_facts)
        assert result.category == "economy"
        assert result.source == "override"
        assert result.confidence == 1.0

    # ------------------------------------------------------------------
    # Task: grounding_facts の theme_category → キーワードより優先
    # ------------------------------------------------------------------
    def test_grounding_facts_overrides_keyword_match(self):
        """security キーワードを含むテーマでも grounding_facts が economy を指定なら economy"""
        theme = "防衛予算と安全保障政策"
        grounding_facts = [{"theme_category": "economy"}]
        result = _estimate_theme_category(theme, grounding_facts=grounding_facts)
        assert result.category == "economy"
        assert result.source == "grounding_facts"

    def test_grounding_facts_category_key_fallback(self):
        """grounding_facts の 'category' キーも theme_category として認識される"""
        theme = "社会保障制度の改革"
        grounding_facts = [{"category": "politics"}]
        result = _estimate_theme_category(theme, grounding_facts=grounding_facts)
        assert result.category == "politics"
        assert result.source == "grounding_facts"

    # ------------------------------------------------------------------
    # Task: MVP 対象カテゴリで低 confidence keyword match → アンカー禁止
    # ------------------------------------------------------------------
    def test_mvp_category_with_low_confidence_disables_anchor(self):
        """economy キーワード 1 件のみ("税") → confidence < 0.4 → is_anchor_eligible=False"""
        # "税制改革" には economy キーワード "税" が 1 件のみ一致
        theme = "税制改革の議論"
        result = _estimate_theme_category(theme)
        assert result.category == "economy"
        assert result.confidence < 0.4
        assert result.is_anchor_eligible is False

    def test_mvp_category_with_high_confidence_enables_anchor(self):
        """economy キーワード 2 件以上 → confidence ≥ 0.4 → is_anchor_eligible=True"""
        # "インフレ" と "賃金" の 2 語が economy に一致
        theme = "インフレと賃金の相関"
        result = _estimate_theme_category(theme)
        assert result.category == "economy"
        assert result.confidence >= 0.4
        assert result.is_anchor_eligible is True

    def test_security_mvp_low_confidence_disables_anchor(self):
        """security キーワード 1 件("テロ") → MVP カテゴリ低 confidence → is_anchor_eligible=False"""
        theme = "テロ対策について考える"
        result = _estimate_theme_category(theme)
        assert result.category == "security"
        assert result.confidence < 0.4
        assert result.is_anchor_eligible is False

    def test_non_mvp_category_low_confidence_still_eligible(self):
        """非 MVP カテゴリ(environment)では低 confidence でも is_anchor_eligible=True"""
        # "環境" 1 件のみ一致 → confidence = 0.2 だが environment は非 MVP
        theme = "環境問題の課題"
        result = _estimate_theme_category(theme)
        assert result.category == "environment"
        assert result.confidence < 0.4
        assert result.is_anchor_eligible is True


# ---------------------------------------------------------------------------
# compare_with_surveys() への theme_category パススルー検証
# ---------------------------------------------------------------------------


class TestCompareWithSurveysThemeCategoryPassthrough:
    """compare_with_surveys() に theme_category を渡すとフィルタリングされること"""

    @pytest.fixture()
    def survey_data_dir(self, tmp_path):
        """economy と security の 2 カテゴリの調査データを用意する"""
        economy_data = {
            "surveys": [
                {
                    "theme": "賃金上昇と景気回復",
                    "question": "賃金が上昇することに賛成ですか？",
                    "source": "テスト経済世論調査2024",
                    "survey_date": "2024-01-01",
                    "sample_size": 1000,
                    "method": "インターネット調査",
                    "theme_category": "economy",
                    "relevance_keywords": ["賃金", "景気", "経済"],
                    "stance_distribution": {
                        "賛成": 0.30,
                        "条件付き賛成": 0.25,
                        "中立": 0.20,
                        "条件付き反対": 0.15,
                        "反対": 0.10,
                    },
                }
            ]
        }
        security_data = {
            "surveys": [
                {
                    "theme": "防衛費拡大と安全保障",
                    "question": "防衛費拡大に賛成ですか？",
                    "source": "テスト安全保障世論調査2024",
                    "survey_date": "2024-01-01",
                    "sample_size": 1000,
                    "method": "インターネット調査",
                    "theme_category": "security",
                    "relevance_keywords": ["防衛", "安全保障", "軍事", "自衛隊"],
                    "stance_distribution": {
                        "賛成": 0.25,
                        "条件付き賛成": 0.20,
                        "中立": 0.25,
                        "条件付き反対": 0.15,
                        "反対": 0.15,
                    },
                }
            ]
        }
        (tmp_path / "economy.yaml").write_text(yaml.dump(economy_data, allow_unicode=True))
        (tmp_path / "security.yaml").write_text(yaml.dump(security_data, allow_unicode=True))
        return str(tmp_path)

    def test_theme_category_filters_to_matching_category_only(self, survey_data_dir):
        """security を指定すると economy 調査は除外され security 調査だけにマッチする"""
        sim_dist = {
            "賛成": 0.25,
            "条件付き賛成": 0.20,
            "中立": 0.25,
            "条件付き反対": 0.15,
            "反対": 0.15,
        }
        report = compare_with_surveys(
            sim_dist,
            "防衛費の拡大と自衛隊の役割",
            survey_data_dir,
            theme_category="security",
        )
        assert report is not None
        for survey in report["matched_surveys"]:
            assert survey["theme_category"] == "security", (
                f"security を指定したが {survey['theme_category']} の調査がマッチした"
            )

    def test_without_theme_category_all_surveys_are_candidates(self, survey_data_dir):
        """theme_category を省略すると全カテゴリが候補になる（後退テスト）"""
        sim_dist = {
            "賛成": 0.28,
            "条件付き賛成": 0.22,
            "中立": 0.22,
            "条件付き反対": 0.15,
            "反対": 0.13,
        }
        # theme_category なしで呼び出しても従来どおり動作する
        report = compare_with_surveys(
            sim_dist,
            "防衛費の拡大と自衛隊の役割",
            survey_data_dir,
        )
        # None または ComparisonReport が返る（クラッシュしないこと）
        assert report is None or isinstance(report, dict)
