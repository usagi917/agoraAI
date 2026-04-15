"""Step 7: theme-aware 初期アンカリング テスト

TDD RED フェーズ:
- preset 解決 → 初期意見分布がアンカー調査と大きく乖離しないテスト
- provenance が DB に正しく記録されるテスト
- category="unknown" 時にアンカリングがスキップされるテスト
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from src.app.database import Base

import src.app.models  # noqa: F401

from src.app.services.society.survey_anchor import (
    apply_survey_anchor,
    get_anchor_distribution,
)
from src.app.services.society.theme_category import ThemeCategoryEstimate
from src.app.utils.distribution_metrics import earth_movers_distance

# ---------------------------------------------------------------------------
# テスト用分布データ
# ---------------------------------------------------------------------------

_SECURITY_ANCHOR = {
    "賛成": 0.45,
    "条件付き賛成": 0.28,
    "中立": 0.12,
    "条件付き反対": 0.09,
    "反対": 0.06,
}
_SIMULATED_FAR = {
    "賛成": 0.10,
    "条件付き賛成": 0.10,
    "中立": 0.10,
    "条件付き反対": 0.35,
    "反対": 0.35,
}


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# =============================================
# Test 1: preset 解決 → アンカー調査との乖離テスト
# =============================================


class TestApplySurveyAnchor:
    """apply_survey_anchor() による分布調整テスト"""

    def test_anchor_reduces_emd_from_anchor(self):
        """アンカー適用後はアンカーとの EMD が小さくなること"""
        anchored = apply_survey_anchor(_SIMULATED_FAR, _SECURITY_ANCHOR, alpha=0.3)

        emd_before = earth_movers_distance(_SIMULATED_FAR, _SECURITY_ANCHOR)
        emd_after = earth_movers_distance(anchored, _SECURITY_ANCHOR)

        assert emd_after < emd_before

    def test_anchored_distribution_is_normalized(self):
        """アンカー適用後の分布の合計が 1.0 であること"""
        anchored = apply_survey_anchor(_SIMULATED_FAR, _SECURITY_ANCHOR, alpha=0.3)
        assert abs(sum(anchored.values()) - 1.0) < 1e-6

    def test_alpha_zero_returns_original_unchanged(self):
        """alpha=0.0 のとき元の分布が変わらないこと"""
        anchored = apply_survey_anchor(_SIMULATED_FAR, _SECURITY_ANCHOR, alpha=0.0)
        for k in _SIMULATED_FAR:
            assert abs(anchored[k] - _SIMULATED_FAR[k]) < 1e-9

    def test_alpha_one_returns_anchor_distribution(self):
        """alpha=1.0 のとき完全にアンカー分布になること"""
        anchored = apply_survey_anchor(_SIMULATED_FAR, _SECURITY_ANCHOR, alpha=1.0)
        for k in _SECURITY_ANCHOR:
            assert abs(anchored[k] - _SECURITY_ANCHOR[k]) < 1e-9


class TestGetAnchorDistribution:
    """get_anchor_distribution() のテスト"""

    def test_returns_valid_distribution_for_matched_surveys(self):
        """マッチする調査がある場合、有効な正規化済み分布が返ること"""
        surveys = [
            {
                "theme": "自衛隊の役割",
                "question": "自衛隊の必要性",
                "source": "テスト調査1",
                "survey_date": "2024-01",
                "sample_size": 1000,
                "method": "web",
                "stance_distribution": _SECURITY_ANCHOR,
                "theme_category": "security",
                "relevance_keywords": ["自衛隊", "防衛", "安全保障"],
            }
        ]

        result = get_anchor_distribution("自衛隊の強化について", "security", surveys)

        assert result is not None
        assert abs(sum(result.values()) - 1.0) < 1e-6
        for key in ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]:
            assert key in result

    def test_returns_average_of_multiple_surveys(self):
        """複数の調査がある場合、平均分布を返すこと"""
        dist_a = {"賛成": 0.40, "条件付き賛成": 0.30, "中立": 0.10, "条件付き反対": 0.10, "反対": 0.10}
        dist_b = {"賛成": 0.20, "条件付き賛成": 0.30, "中立": 0.20, "条件付き反対": 0.20, "反対": 0.10}
        surveys = [
            {
                "theme": "防衛費増額",
                "question": "防衛費を増やすことに賛成ですか",
                "source": "テスト調査A",
                "survey_date": "2024-01",
                "sample_size": 1000,
                "method": "web",
                "stance_distribution": dist_a,
                "theme_category": "security",
                "relevance_keywords": ["防衛費", "防衛"],
            },
            {
                "theme": "防衛政策",
                "question": "防衛政策に賛成ですか",
                "source": "テスト調査B",
                "survey_date": "2024-02",
                "sample_size": 800,
                "method": "web",
                "stance_distribution": dist_b,
                "theme_category": "security",
                "relevance_keywords": ["防衛", "軍事"],
            },
        ]

        result = get_anchor_distribution("防衛費の増額", "security", surveys)

        assert result is not None
        # 賛成は 2調査の平均
        assert abs(result["賛成"] - (0.40 + 0.20) / 2) < 0.05

    def test_returns_none_when_no_surveys(self):
        """調査リストが空の場合は None を返すこと"""
        result = get_anchor_distribution("ほげほげ政策", "economy", [])
        assert result is None

    def test_returns_none_when_no_surveys_match(self):
        """テーマに一致する調査がない場合は None を返すこと"""
        surveys = [
            {
                "theme": "自衛隊の役割",
                "question": "自衛隊の必要性",
                "source": "テスト調査1",
                "survey_date": "2024-01",
                "sample_size": 1000,
                "method": "web",
                "stance_distribution": _SECURITY_ANCHOR,
                "theme_category": "security",
                "relevance_keywords": ["自衛隊", "防衛"],
            }
        ]

        result = get_anchor_distribution("ほげほげ政策", "security", surveys)
        assert result is None


# =============================================
# Test 2: provenance が DB に正しく記録されるテスト
# =============================================


class TestRegisterResultSavesProvenance:
    """register_result() で ThemeCategoryEstimate の provenance が DB に保存されること"""

    @pytest.mark.asyncio
    async def test_saves_confidence_and_source_to_db(self, db_session):
        """confidence と source が ValidationRecord に永続化されること"""
        from src.app.services.society.validation_pipeline import register_result

        estimate = ThemeCategoryEstimate(
            category="security",
            confidence=0.8,
            source="grounding_facts",
            is_anchor_eligible=True,
        )
        distribution = {
            "賛成": 0.30,
            "条件付き賛成": 0.25,
            "中立": 0.20,
            "条件付き反対": 0.15,
            "反対": 0.10,
        }

        record = await register_result(
            db_session,
            simulation_id="sim-step7-001",
            theme="防衛費増額に関する議論",
            theme_category="security",
            distribution=distribution,
            theme_category_estimate=estimate,
        )

        assert record.theme_category_confidence == 0.8
        assert record.theme_category_source == "grounding_facts"

    @pytest.mark.asyncio
    async def test_saves_keyword_match_provenance(self, db_session):
        """keyword_match source でも正しく保存されること"""
        from src.app.services.society.validation_pipeline import register_result

        estimate = ThemeCategoryEstimate(
            category="economy",
            confidence=0.4,
            source="keyword_match",
            is_anchor_eligible=True,
        )
        distribution = {
            "賛成": 0.25,
            "条件付き賛成": 0.30,
            "中立": 0.20,
            "条件付き反対": 0.15,
            "反対": 0.10,
        }

        record = await register_result(
            db_session,
            simulation_id="sim-step7-002",
            theme="物価上昇対策",
            theme_category="economy",
            distribution=distribution,
            theme_category_estimate=estimate,
        )

        assert record.theme_category_confidence == 0.4
        assert record.theme_category_source == "keyword_match"

    @pytest.mark.asyncio
    async def test_none_estimate_leaves_provenance_fields_null(self, db_session):
        """theme_category_estimate=None のとき confidence/source が NULL のままであること"""
        from src.app.services.society.validation_pipeline import register_result

        distribution = {
            "賛成": 0.25,
            "条件付き賛成": 0.30,
            "中立": 0.20,
            "条件付き反対": 0.15,
            "反対": 0.10,
        }

        record = await register_result(
            db_session,
            simulation_id="sim-step7-003",
            theme="テスト政策",
            theme_category="unknown",
            distribution=distribution,
            theme_category_estimate=None,
        )

        assert record.theme_category_confidence is None
        assert record.theme_category_source is None


# =============================================
# Test 3: category="unknown" 時にアンカリングがスキップされるテスト
# =============================================


class TestUnknownCategorySkipsAnchoring:
    """category="unknown" のときアンカリングがスキップされること"""

    def test_none_anchor_returns_original_distribution_unchanged(self):
        """anchor_distribution=None のとき元の分布がそのまま返ること"""
        original = {
            "賛成": 0.30,
            "条件付き賛成": 0.25,
            "中立": 0.20,
            "条件付き反対": 0.15,
            "反対": 0.10,
        }

        result = apply_survey_anchor(original, None)
        assert result == original

    def test_unknown_theme_estimate_is_not_anchor_eligible(self):
        """どのカテゴリキーワードにもマッチしないテーマ文は category='unknown', is_anchor_eligible=False になること"""
        from src.app.services.society.society_orchestrator import _estimate_theme_category

        estimate = _estimate_theme_category("バナナの輸入量と熱帯果物の流通について")

        assert estimate.category == "unknown"
        assert estimate.is_anchor_eligible is False

    def test_not_anchor_eligible_results_in_no_distribution_change(self):
        """is_anchor_eligible=False のとき分布が変更されないこと（オーケストレータの判定ロジック検証）"""
        original = {
            "賛成": 0.30,
            "条件付き賛成": 0.25,
            "中立": 0.20,
            "条件付き反対": 0.15,
            "反対": 0.10,
        }
        some_anchor = {
            "賛成": 0.50,
            "条件付き賛成": 0.20,
            "中立": 0.10,
            "条件付き反対": 0.10,
            "反対": 0.10,
        }

        estimate = ThemeCategoryEstimate(
            category="unknown",
            confidence=0.0,
            source="fallback",
            is_anchor_eligible=False,
        )

        # オーケストレータはこの判定をする: is_anchor_eligible=False → anchor=None
        anchor_dist = some_anchor if estimate.is_anchor_eligible else None
        result = apply_survey_anchor(original, anchor_dist)

        assert result == original
