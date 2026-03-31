"""survey_anchor モジュールのテスト

世論調査アンカリング: YAML読み込み、キーワードマッチング、KL-divergence、EMD、比較レポート
"""

import os
import math
import pytest

from src.app.services.society.survey_anchor import (
    SurveyRecord,
    ComparisonReport,
    load_survey_data,
    find_relevant_surveys,
    kl_divergence_symmetric,
    earth_movers_distance,
    compare_with_surveys,
    map_to_five_stances,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_YAML = os.path.join(FIXTURES_DIR, "survey_data_sample.yaml")


class TestLoadSurveyData:
    def test_load_survey_data(self):
        """fixtures/survey_data_sample.yaml を読み込み、list[SurveyRecord] が返る"""
        surveys = load_survey_data(FIXTURES_DIR)
        assert isinstance(surveys, list)
        assert len(surveys) >= 2
        for s in surveys:
            assert "theme" in s
            assert "question" in s
            assert "source" in s
            assert "survey_date" in s
            assert "sample_size" in s
            assert "method" in s
            assert "stance_distribution" in s
            assert "theme_category" in s
            assert "relevance_keywords" in s

    def test_load_survey_data_validates_required_fields(self, tmp_path):
        """必須フィールド欠損時に ValueError が出る"""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "surveys:\n"
            "  - theme: test\n"
            "    question: test\n"
            # source が欠損
        )
        with pytest.raises(ValueError, match="source"):
            load_survey_data(str(tmp_path))

    def test_load_survey_data_validates_distribution_sums_to_one(self, tmp_path):
        """stance_distribution の合計が1.0±0.01でない場合にエラー"""
        bad_yaml = tmp_path / "bad_dist.yaml"
        bad_yaml.write_text(
            "surveys:\n"
            "  - theme: test\n"
            "    question: test\n"
            "    source: test\n"
            "    survey_date: '2024-01'\n"
            "    sample_size: 100\n"
            "    method: test\n"
            "    theme_category: social\n"
            "    relevance_keywords: [test]\n"
            "    stance_distribution:\n"
            "      賛成: 0.50\n"
            "      条件付き賛成: 0.20\n"
            "      中立: 0.10\n"
            "      条件付き反対: 0.05\n"
            "      反対: 0.05\n"  # 合計 0.90 != 1.0
        )
        with pytest.raises(ValueError, match="1.0"):
            load_survey_data(str(tmp_path))

    def test_load_survey_data_rejects_missing_stance_labels(self, tmp_path):
        """必須5スタンスのいずれかが欠けた分布は reject する"""
        bad_yaml = tmp_path / "missing_stance.yaml"
        bad_yaml.write_text(
            "surveys:\n"
            "  - theme: test\n"
            "    question: test\n"
            "    source: test\n"
            "    survey_date: '2024-01'\n"
            "    sample_size: 100\n"
            "    method: test\n"
            "    theme_category: social\n"
            "    relevance_keywords: [test]\n"
            "    stance_distribution:\n"
            "      賛成: 0.40\n"
            "      条件付き賛成: 0.20\n"
            "      中立: 0.20\n"
            "      条件付き反対: 0.20\n"
        )
        with pytest.raises(ValueError, match="Missing stance keys"):
            load_survey_data(str(tmp_path))


class TestFindRelevantSurveys:
    def test_find_relevant_surveys_by_keyword(self):
        """テーマキーワードで関連調査が返る"""
        surveys = load_survey_data(FIXTURES_DIR)
        results = find_relevant_surveys("外交", surveys)
        assert len(results) >= 1
        assert any("外交" in s["theme"] or "外交" in " ".join(s["relevance_keywords"]) for s in results)

    def test_find_relevant_surveys_returns_empty_on_no_match(self):
        """無関連キーワードで空リスト"""
        surveys = load_survey_data(FIXTURES_DIR)
        results = find_relevant_surveys("zzz_存在しないテーマ_zzz", surveys)
        assert results == []

    def test_find_relevant_surveys_respects_top_k(self):
        """top_k=1 で最大1件"""
        surveys = load_survey_data(FIXTURES_DIR)
        results = find_relevant_surveys("防衛", surveys, top_k=1)
        assert len(results) <= 1


class TestKLDivergenceSymmetric:
    def test_kl_divergence_symmetric_identical(self):
        """同一分布でKL≈0"""
        p = {"賛成": 0.3, "条件付き賛成": 0.2, "中立": 0.2, "条件付き反対": 0.2, "反対": 0.1}
        result = kl_divergence_symmetric(p, p)
        assert result < 0.001

    def test_kl_divergence_symmetric_different(self):
        """異なる分布でKL>0"""
        p = {"賛成": 0.5, "条件付き賛成": 0.2, "中立": 0.1, "条件付き反対": 0.1, "反対": 0.1}
        q = {"賛成": 0.1, "条件付き賛成": 0.1, "中立": 0.1, "条件付き反対": 0.2, "反対": 0.5}
        result = kl_divergence_symmetric(p, q)
        assert result > 0.1

    def test_kl_divergence_symmetric_with_zero_probability(self):
        """スムージングでゼロ除算回避"""
        p = {"賛成": 1.0, "条件付き賛成": 0.0, "中立": 0.0, "条件付き反対": 0.0, "反対": 0.0}
        q = {"賛成": 0.0, "条件付き賛成": 0.0, "中立": 0.0, "条件付き反対": 0.0, "反対": 1.0}
        result = kl_divergence_symmetric(p, q)
        assert math.isfinite(result)
        assert result > 0


class TestEarthMoversDistance:
    def test_earth_movers_distance_identical(self):
        """同一分布でEMD=0"""
        p = {"賛成": 0.3, "条件付き賛成": 0.2, "中立": 0.2, "条件付き反対": 0.2, "反対": 0.1}
        result = earth_movers_distance(p, p)
        assert abs(result) < 1e-9

    def test_earth_movers_distance_opposite(self):
        """賛成100% vs 反対100% で最大EMD"""
        p = {"賛成": 1.0, "条件付き賛成": 0.0, "中立": 0.0, "条件付き反対": 0.0, "反対": 0.0}
        q = {"賛成": 0.0, "条件付き賛成": 0.0, "中立": 0.0, "条件付き反対": 0.0, "反対": 1.0}
        result = earth_movers_distance(p, q)
        assert result > 0
        # 序数距離4で最大
        assert abs(result - 4.0) < 1e-9

    def test_earth_movers_distance_ordinal_aware(self):
        """隣接スタンス間 < 離れたスタンス間"""
        base = {"賛成": 0.5, "条件付き賛成": 0.5, "中立": 0.0, "条件付き反対": 0.0, "反対": 0.0}
        near = {"賛成": 0.0, "条件付き賛成": 0.5, "中立": 0.5, "条件付き反対": 0.0, "反対": 0.0}
        far = {"賛成": 0.0, "条件付き賛成": 0.0, "中立": 0.0, "条件付き反対": 0.5, "反対": 0.5}
        emd_near = earth_movers_distance(base, near)
        emd_far = earth_movers_distance(base, far)
        assert emd_near < emd_far


class TestCompareWithSurveys:
    def test_compare_with_surveys(self):
        """ComparisonReport の構造検証"""
        sim_dist = {"賛成": 0.30, "条件付き賛成": 0.20, "中立": 0.25, "条件付き反対": 0.15, "反対": 0.10}
        report = compare_with_surveys(sim_dist, "外交", FIXTURES_DIR)
        assert report is not None
        assert "theme" in report
        assert "matched_surveys" in report
        assert "kl_divergence" in report
        assert "emd" in report
        assert "per_survey_deviations" in report
        assert len(report["matched_surveys"]) >= 1

    def test_compare_with_surveys_no_data(self, tmp_path):
        """調査データなしで None"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        sim_dist = {"賛成": 0.30, "条件付き賛成": 0.20, "中立": 0.25, "条件付き反対": 0.15, "反対": 0.10}
        report = compare_with_surveys(sim_dist, "外交", str(empty_dir))
        assert report is None


class TestStanceMapping:
    def test_stance_mapping_from_binary(self):
        """賛成/反対の2択を5段階に変換"""
        original = {"賛成": 0.6, "反対": 0.4}
        result = map_to_five_stances(original, "binary")
        assert set(result.keys()) == {"賛成", "条件付き賛成", "中立", "条件付き反対", "反対"}
        assert abs(sum(result.values()) - 1.0) < 0.01

    def test_stance_mapping_from_likert_5(self):
        """5段階リッカートをスタンスにマップ"""
        original = {"非常にそう思う": 0.2, "そう思う": 0.3, "どちらとも": 0.2, "そう思わない": 0.2, "全くそう思わない": 0.1}
        result = map_to_five_stances(original, "likert_5")
        assert set(result.keys()) == {"賛成", "条件付き賛成", "中立", "条件付き反対", "反対"}
        assert abs(sum(result.values()) - 1.0) < 0.01
