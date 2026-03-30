"""provenance.py のテスト (TDD RED phase)

テスト対象: backend/src/app/services/society/provenance.py
"""

import pytest
from src.app.services.society.provenance import build_provenance, _get_git_hash


# ---------------------------------------------------------------------------
# Required sections
# ---------------------------------------------------------------------------


class TestProvenanceStructure:
    def test_provenance_has_required_sections(self):
        """返り値に全ての必須セクションが存在する"""
        result = build_provenance(
            population_size=1000,
            selected_count=100,
            effective_sample_size=85.0,
        )
        required_keys = [
            "methodology",
            "data_sources",
            "parameters",
            "quality_metrics",
            "limitations",
            "reproducibility",
        ]
        for key in required_keys:
            assert key in result, f"Missing required section: '{key}'"

    def test_provenance_data_sources_is_list(self):
        """data_sources がリストで各要素に 'name', 'used_for' キーを持つ"""
        result = build_provenance(
            population_size=500,
            selected_count=50,
            effective_sample_size=42.0,
        )
        sources = result["data_sources"]
        assert isinstance(sources, list), "data_sources must be a list"
        assert len(sources) > 0, "data_sources must not be empty"
        for source in sources:
            assert "name" in source, f"Source missing 'name': {source}"
            assert "used_for" in source, f"Source missing 'used_for': {source}"


# ---------------------------------------------------------------------------
# Methodology section
# ---------------------------------------------------------------------------


class TestProvenanceMethodology:
    def test_provenance_methodology_cites_fishkin(self):
        """methodology['citation'] に 'Fishkin' を含む"""
        result = build_provenance(
            population_size=1000,
            selected_count=100,
            effective_sample_size=85.0,
        )
        citation = result["methodology"]["citation"]
        assert "Fishkin" in citation, f"Expected 'Fishkin' in citation, got: '{citation}'"

    def test_provenance_methodology_has_framework(self):
        """methodology['framework'] が空でない"""
        result = build_provenance(
            population_size=1000,
            selected_count=100,
            effective_sample_size=85.0,
        )
        framework = result["methodology"].get("framework", "")
        assert framework, "methodology['framework'] must not be empty"


# ---------------------------------------------------------------------------
# Parameters section
# ---------------------------------------------------------------------------


class TestProvenanceParameters:
    def test_provenance_parameters_match_input(self):
        """入力した population_size, selected_count, meeting_rounds が parameters に正しく反映"""
        meeting_params = {"num_rounds": 5, "participants": 12}
        result = build_provenance(
            population_size=2000,
            selected_count=150,
            effective_sample_size=130.0,
            meeting_params=meeting_params,
        )
        params = result["parameters"]
        assert params["population_size"] == 2000
        assert params["selected_sample_size"] == 150
        assert params["effective_sample_size"] == 130.0
        assert params["meeting_rounds"] == 5

    def test_provenance_parameters_default_meeting_rounds(self):
        """meeting_params が None のとき meeting_rounds のデフォルト値が 3"""
        result = build_provenance(
            population_size=500,
            selected_count=50,
            effective_sample_size=45.0,
        )
        assert result["parameters"]["meeting_rounds"] == 3

    def test_provenance_parameters_seed_preserved(self):
        """seed が parameters と reproducibility 両方に記録される"""
        result = build_provenance(
            population_size=500,
            selected_count=50,
            effective_sample_size=45.0,
            seed=42,
        )
        assert result["parameters"]["random_seed"] == 42
        assert result["reproducibility"]["random_seed"] == 42


# ---------------------------------------------------------------------------
# Limitations section — dynamic additions
# ---------------------------------------------------------------------------


class TestProvenanceLimitations:
    def test_provenance_adds_dynamic_limitation(self):
        """effective_sample_size < 30 のとき limitations に標本不足の警告が追加される"""
        result = build_provenance(
            population_size=100,
            selected_count=20,
            effective_sample_size=15.0,  # < 30
        )
        limitations = result["limitations"]
        low_sample_warning_present = any(
            "有効標本" in lim or "30" in lim or "標本" in lim
            for lim in limitations
        )
        assert low_sample_warning_present, (
            "Expected low-sample warning in limitations when n_eff < 30, "
            f"got: {limitations}"
        )

    def test_provenance_no_dynamic_limitation_when_sufficient(self):
        """effective_sample_size >= 30 のとき動的制約は追加されない（固定制約のみ）"""
        result_sufficient = build_provenance(
            population_size=1000,
            selected_count=100,
            effective_sample_size=80.0,  # >= 30
        )
        result_insufficient = build_provenance(
            population_size=100,
            selected_count=20,
            effective_sample_size=15.0,  # < 30
        )
        # 十分なサンプルサイズの場合の limitations 件数 < 不十分な場合の件数
        assert len(result_sufficient["limitations"]) < len(result_insufficient["limitations"]), (
            "Sufficient n_eff should produce fewer limitations than insufficient n_eff"
        )

    def test_provenance_limitations_warn_on_provider_bias(self):
        """provider_bias_detected=True で呼ぶと limitations にプロバイダバイアス警告が追加"""
        result = build_provenance(
            population_size=1000,
            selected_count=100,
            effective_sample_size=85.0,
            provider_bias_detected=True,
        )
        limitations = result["limitations"]
        bias_warning_present = any(
            "プロバイダ" in lim or "バイアス" in lim or "bias" in lim.lower()
            for lim in limitations
        )
        assert bias_warning_present, (
            "Expected provider bias warning in limitations when provider_bias_detected=True, "
            f"got: {limitations}"
        )

    def test_provenance_no_bias_warning_when_not_detected(self):
        """provider_bias_detected=False (デフォルト) ではバイアス警告なし"""
        result = build_provenance(
            population_size=1000,
            selected_count=100,
            effective_sample_size=85.0,
            provider_bias_detected=False,
        )
        limitations = result["limitations"]
        bias_warning_present = any(
            "プロバイダ" in lim or "バイアス" in lim
            for lim in limitations
        )
        assert not bias_warning_present, (
            "Unexpected provider bias warning when provider_bias_detected=False, "
            f"got: {limitations}"
        )


# ---------------------------------------------------------------------------
# Reproducibility section
# ---------------------------------------------------------------------------


class TestProvenanceReproducibility:
    def test_provenance_includes_git_hash(self):
        """reproducibility['code_version'] が空文字列でない（gitリポジトリ内なので取得できる）"""
        result = build_provenance(
            population_size=500,
            selected_count=50,
            effective_sample_size=45.0,
        )
        code_version = result["reproducibility"].get("code_version", "")
        assert code_version != "", (
            "reproducibility['code_version'] must not be empty in a git repository"
        )

    def test_provenance_includes_timestamp(self):
        """reproducibility['timestamp'] が存在し ISO 形式（末尾 'Z'）"""
        result = build_provenance(
            population_size=500,
            selected_count=50,
            effective_sample_size=45.0,
        )
        timestamp = result["reproducibility"].get("timestamp", "")
        assert timestamp, "reproducibility['timestamp'] must not be empty"
        # ISO 8601 形式チェック: "YYYY-MM-DDTHH:MM:SS.ffffffZ" or "YYYY-MM-DDTHH:MM:SSZ"
        assert "T" in timestamp, f"Expected ISO format with 'T', got: '{timestamp}'"
        assert timestamp.endswith("Z"), f"Expected timestamp ending with 'Z', got: '{timestamp}'"


# ---------------------------------------------------------------------------
# _get_git_hash utility
# ---------------------------------------------------------------------------


class TestGetGitHash:
    def test_get_git_hash_returns_nonempty_string(self):
        """_get_git_hash() が空でない文字列を返す"""
        result = _get_git_hash()
        assert isinstance(result, str)
        assert result != "", "_get_git_hash() must return a non-empty string"

    def test_get_git_hash_not_unknown_in_git_repo(self):
        """gitリポジトリ内なので 'unknown' にならない"""
        result = _get_git_hash()
        assert result != "unknown", (
            "_get_git_hash() returned 'unknown' but we are inside a git repository"
        )


# ---------------------------------------------------------------------------
# grounding_sources passthrough
# ---------------------------------------------------------------------------


class TestProvenanceGroundingSources:
    def test_provenance_appends_grounding_sources(self):
        """grounding_sources が渡されると data_sources に追加される"""
        extra_sources = [
            {"name": "内閣府 2022 調査", "used_for": "満足度指標"},
            {"name": "厚労省 2023 統計", "used_for": "雇用率"},
        ]
        result = build_provenance(
            population_size=500,
            selected_count=50,
            effective_sample_size=45.0,
            grounding_sources=extra_sources,
        )
        source_names = [s["name"] for s in result["data_sources"]]
        assert "内閣府 2022 調査" in source_names
        assert "厚労省 2023 統計" in source_names

    def test_provenance_no_extra_sources_when_none(self):
        """grounding_sources=None のとき組み込みソースのみ"""
        result_no_extra = build_provenance(
            population_size=500,
            selected_count=50,
            effective_sample_size=45.0,
            grounding_sources=None,
        )
        result_with_extra = build_provenance(
            population_size=500,
            selected_count=50,
            effective_sample_size=45.0,
            grounding_sources=[{"name": "追加ソース", "used_for": "テスト"}],
        )
        assert len(result_with_extra["data_sources"]) > len(result_no_extra["data_sources"])


# ---------------------------------------------------------------------------
# quality_metrics passthrough
# ---------------------------------------------------------------------------


class TestProvenanceQualityMetrics:
    def test_provenance_quality_metrics_passthrough(self):
        """quality_metrics が渡されるとそのまま返り値に含まれる"""
        metrics = {"accuracy": 0.95, "f1": 0.88}
        result = build_provenance(
            population_size=500,
            selected_count=50,
            effective_sample_size=45.0,
            quality_metrics=metrics,
        )
        assert result["quality_metrics"] == metrics

    def test_provenance_quality_metrics_defaults_to_empty(self):
        """quality_metrics=None のとき空辞書"""
        result = build_provenance(
            population_size=500,
            selected_count=50,
            effective_sample_size=45.0,
        )
        assert result["quality_metrics"] == {}
