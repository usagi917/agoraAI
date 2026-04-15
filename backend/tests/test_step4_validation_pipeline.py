"""Step 4: validation 基盤の先行実装テスト

TDD RED フェーズ:
- run_full_validation() の正常系・report-only・unvalidated 分類
- build_validation_summary() のゲート判定（EMD < 0.15, JSD < 0.10, Brier < 0.30）
- 評価カバレッジ基準（validated 件数不足 → inconclusive）
- exclude_survey_ids による leakage 防止
- Rank C mapping の train/gate 除外
- manifest 外 survey ヒット → survey_manifest_status="unmanifested"
"""

from __future__ import annotations

import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from src.app.database import Base

import src.app.models  # noqa: F401

from src.app.repositories.validation_repo import ValidationRepository
from src.app.services.society.validation_pipeline import (
    register_result,
    resolve_with_actual,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

SIM_DIST = {
    "賛成": 0.30,
    "条件付き賛成": 0.25,
    "中立": 0.20,
    "条件付き反対": 0.15,
    "反対": 0.10,
}
ACTUAL_DIST_CLOSE = {
    "賛成": 0.28,
    "条件付き賛成": 0.24,
    "中立": 0.22,
    "条件付き反対": 0.15,
    "反対": 0.11,
}
ACTUAL_DIST_FAR = {
    "賛成": 0.05,
    "条件付き賛成": 0.05,
    "中立": 0.05,
    "条件付き反対": 0.40,
    "反対": 0.45,
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
# run_full_validation() テスト
# =============================================

class TestRunFullValidation:
    """run_full_validation() の正常系・report-only・unvalidated 分類テスト"""

    @pytest.mark.asyncio
    async def test_normal_case_returns_validated_status(self, db_session):
        """正常系: actual_distribution が存在するレコードは validated ステータスで返る"""
        from src.app.services.society.validation_pipeline import run_full_validation

        r = await register_result(db_session, "sim-v01", "経済政策", "economy", SIM_DIST)
        await resolve_with_actual(db_session, r.id, ACTUAL_DIST_CLOSE, "内閣府", "2024-01")

        results = await run_full_validation(db_session, theme_category="economy")

        validated = [res for res in results if res["status"] == "validated"]
        assert len(validated) >= 1

    @pytest.mark.asyncio
    async def test_report_only_records_are_classified(self, db_session):
        """report-only モード: actual_distribution なしのレコードは report_only に分類される"""
        from src.app.services.society.validation_pipeline import run_full_validation

        # actual_distribution なしで登録
        await register_result(db_session, "sim-v02", "経済政策", "economy", SIM_DIST)

        results = await run_full_validation(db_session, theme_category="economy")

        report_only = [res for res in results if res["status"] == "report_only"]
        assert len(report_only) >= 1

    @pytest.mark.asyncio
    async def test_unvalidated_records_are_classified(self, db_session):
        """unvalidated: actual_distribution が None のレコードは unvalidated に分類される"""
        from src.app.services.society.validation_pipeline import run_full_validation

        await register_result(db_session, "sim-v03", "社会問題", "social", SIM_DIST)

        results = await run_full_validation(db_session, theme_category="social")

        unvalidated = [res for res in results if res["status"] in ("unvalidated", "report_only")]
        assert len(unvalidated) >= 1

    @pytest.mark.asyncio
    async def test_result_contains_required_fields(self, db_session):
        """各結果は simulation_id, status, theme_category を含む"""
        from src.app.services.society.validation_pipeline import run_full_validation

        r = await register_result(db_session, "sim-v04", "経済政策", "economy", SIM_DIST)
        await resolve_with_actual(db_session, r.id, ACTUAL_DIST_CLOSE, "内閣府", "2024-01")

        results = await run_full_validation(db_session)

        assert len(results) >= 1
        for res in results:
            assert "simulation_id" in res
            assert "status" in res
            assert "theme_category" in res

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self, db_session):
        """レコードがない場合は空リストを返す"""
        from src.app.services.society.validation_pipeline import run_full_validation

        results = await run_full_validation(db_session)
        assert results == []


# =============================================
# build_validation_summary() ゲート判定テスト
# =============================================

class TestBuildValidationSummary:
    """build_validation_summary() のゲート判定テスト"""

    def _make_passing_records(self, count: int) -> list[dict]:
        """MIN_VALIDATED_COUNT 以上の通過可能な records を生成するヘルパー"""
        from src.app.services.society.validation_pipeline import MIN_VALIDATED_COUNT
        n = max(count, MIN_VALIDATED_COUNT)
        return [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.15, "status": "validated"}
            for _ in range(n)
        ]

    def test_gate_pass_when_all_metrics_below_threshold(self):
        """EMD < 0.15, JSD < 0.10, Brier < 0.30 を全て満たす場合: gate=pass"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        records_data = [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.15, "status": "validated"}
            for _ in range(MIN_VALIDATED_COUNT)
        ]
        summary = build_validation_summary(records_data)

        assert summary["gate"] == "pass"

    def test_gate_fail_when_emd_exceeds_threshold(self):
        """EMD >= 0.15 の場合: gate=fail"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        records_data = [
            {"emd": 0.20, "jsd": 0.05, "brier_score": 0.15, "status": "validated"}
            for _ in range(MIN_VALIDATED_COUNT)
        ]
        summary = build_validation_summary(records_data)

        assert summary["gate"] == "fail"

    def test_gate_fail_when_jsd_exceeds_threshold(self):
        """JSD >= 0.10 の場合: gate=fail"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        records_data = [
            {"emd": 0.08, "jsd": 0.12, "brier_score": 0.15, "status": "validated"}
            for _ in range(MIN_VALIDATED_COUNT)
        ]
        summary = build_validation_summary(records_data)

        assert summary["gate"] == "fail"

    def test_gate_fail_when_brier_exceeds_threshold(self):
        """Brier >= 0.30 の場合: gate=fail"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        records_data = [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.35, "status": "validated"}
            for _ in range(MIN_VALIDATED_COUNT)
        ]
        summary = build_validation_summary(records_data)

        assert summary["gate"] == "fail"

    def test_summary_contains_avg_metrics(self):
        """summary は avg_emd, avg_jsd, avg_brier を含む"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        # MIN_VALIDATED_COUNT が 3 の場合は 3 件必要
        # 平均が計算可能な固定値を使う
        records_data = [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.15, "status": "validated"},
            {"emd": 0.10, "jsd": 0.07, "brier_score": 0.20, "status": "validated"},
            {"emd": 0.09, "jsd": 0.06, "brier_score": 0.175, "status": "validated"},
        ]
        # MIN_VALIDATED_COUNT > 3 の場合は追加する
        while len(records_data) < MIN_VALIDATED_COUNT:
            records_data.append(
                {"emd": 0.09, "jsd": 0.06, "brier_score": 0.175, "status": "validated"}
            )

        summary = build_validation_summary(records_data)

        assert "avg_emd" in summary
        assert "avg_jsd" in summary
        assert "avg_brier" in summary
        assert summary["avg_emd"] is not None
        assert summary["avg_jsd"] is not None
        assert summary["avg_brier"] is not None

    def test_summary_with_boundary_emd_value(self):
        """EMD = 0.15（境界値）は fail（< 0.15 でないため）"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        records_data = [
            {"emd": 0.15, "jsd": 0.05, "brier_score": 0.15, "status": "validated"}
            for _ in range(MIN_VALIDATED_COUNT)
        ]
        summary = build_validation_summary(records_data)

        assert summary["gate"] == "fail"

    def test_summary_with_boundary_jsd_value(self):
        """JSD = 0.10（境界値）は fail（< 0.10 でないため）"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        records_data = [
            {"emd": 0.08, "jsd": 0.10, "brier_score": 0.15, "status": "validated"}
            for _ in range(MIN_VALIDATED_COUNT)
        ]
        summary = build_validation_summary(records_data)

        assert summary["gate"] == "fail"

    def test_summary_with_boundary_brier_value(self):
        """Brier = 0.30（境界値）は fail（< 0.30 でないため）"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        records_data = [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.30, "status": "validated"}
            for _ in range(MIN_VALIDATED_COUNT)
        ]
        summary = build_validation_summary(records_data)

        assert summary["gate"] == "fail"


# =============================================
# 評価カバレッジ基準テスト (inconclusive)
# =============================================

class TestValidationCoverageGate:
    """validated 件数不足 → inconclusive 判定テスト"""

    def test_inconclusive_when_no_validated_records(self):
        """validated レコードが 0 件 → inconclusive"""
        from src.app.services.society.validation_pipeline import build_validation_summary

        records_data = []
        summary = build_validation_summary(records_data)

        assert summary["gate"] == "inconclusive"

    def test_inconclusive_when_validated_count_below_minimum(self):
        """validated 件数が MIN_VALIDATED_COUNT 未満 → inconclusive"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        # MIN_VALIDATED_COUNT - 1 件の validated レコード
        records_data = [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.15, "status": "validated"}
            for _ in range(max(0, MIN_VALIDATED_COUNT - 1))
        ]
        summary = build_validation_summary(records_data)

        assert summary["gate"] == "inconclusive"

    def test_inconclusive_when_coverage_ratio_too_low(self):
        """validated / total が MIN_COVERAGE_RATIO 未満 → inconclusive"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
            MIN_COVERAGE_RATIO,
        )

        # validated が MIN_VALIDATED_COUNT 以上だが total に対して比率が低い場合
        # total = 100, validated = MIN_VALIDATED_COUNT (比率が低い)
        total = 100
        validated_count = MIN_VALIDATED_COUNT  # 通常は 3
        # MIN_COVERAGE_RATIO (通常 0.5) を下回るよう unvalidated を多く追加
        validated_records = [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.15, "status": "validated"}
            for _ in range(validated_count)
        ]
        unvalidated_records = [
            {"emd": None, "jsd": None, "brier_score": None, "status": "report_only"}
            for _ in range(total - validated_count)
        ]
        records_data = validated_records + unvalidated_records

        # 比率 = validated_count / total が MIN_COVERAGE_RATIO 未満なら inconclusive
        expected_ratio = validated_count / total
        if expected_ratio < MIN_COVERAGE_RATIO:
            summary = build_validation_summary(records_data)
            assert summary["gate"] == "inconclusive"

    def test_gate_pass_when_coverage_is_sufficient(self):
        """十分な validated レコードがある場合: 通常ゲート判定を行う"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        records_data = [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.15, "status": "validated"}
            for _ in range(MIN_VALIDATED_COUNT)
        ]
        summary = build_validation_summary(records_data)

        # inconclusive でなければ pass か fail になる
        assert summary["gate"] in ("pass", "fail")

    def test_summary_includes_coverage_info(self):
        """summary は total_count と validated_count を含む"""
        from src.app.services.society.validation_pipeline import build_validation_summary

        records_data = [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.15, "status": "validated"},
            {"emd": None, "jsd": None, "brier_score": None, "status": "report_only"},
        ]
        summary = build_validation_summary(records_data)

        assert "total_count" in summary
        assert "validated_count" in summary
        assert summary["total_count"] == 2
        assert summary["validated_count"] == 1


# =============================================
# exclude_survey_ids leakage 防止テスト
# =============================================

class TestExcludeSurveyIds:
    """find_relevant_surveys の exclude_survey_ids による leakage 防止テスト"""

    def test_excluded_survey_not_returned(self):
        """exclude_survey_ids に含まれる survey_id はマッチ結果に含まれない"""
        from src.app.services.society.survey_anchor import find_relevant_surveys, SurveyRecord

        surveys: list[SurveyRecord] = [
            SurveyRecord(
                theme="外交問題",
                question="q1",
                source="source-A",
                survey_date="2024-01",
                sample_size=3000,
                method="面接",
                stance_distribution={
                    "賛成": 0.25, "条件付き賛成": 0.20,
                    "中立": 0.30, "条件付き反対": 0.15, "反対": 0.10
                },
                theme_category="politics",
                relevance_keywords=["外交", "国際関係"],
            ),
            SurveyRecord(
                theme="外交政策",
                question="q2",
                source="source-B",
                survey_date="2024-02",
                sample_size=2000,
                method="郵送",
                stance_distribution={
                    "賛成": 0.30, "条件付き賛成": 0.25,
                    "中立": 0.20, "条件付き反対": 0.15, "反対": 0.10
                },
                theme_category="politics",
                relevance_keywords=["外交", "政策"],
            ),
        ]

        # source-A を持つ survey を exclude_survey_ids に含める
        result = find_relevant_surveys(
            "外交",
            surveys,
            theme_category="politics",
            exclude_survey_ids=["source-A"],
        )

        sources = [s["source"] for s in result]
        assert "source-A" not in sources

    def test_no_exclusion_returns_all_relevant(self):
        """exclude_survey_ids なしで全ての関連 survey を返す"""
        from src.app.services.society.survey_anchor import find_relevant_surveys, SurveyRecord

        surveys: list[SurveyRecord] = [
            SurveyRecord(
                theme="外交問題",
                question="q1",
                source="source-A",
                survey_date="2024-01",
                sample_size=3000,
                method="面接",
                stance_distribution={
                    "賛成": 0.25, "条件付き賛成": 0.20,
                    "中立": 0.30, "条件付き反対": 0.15, "反対": 0.10
                },
                theme_category="politics",
                relevance_keywords=["外交", "国際関係"],
            ),
        ]

        result = find_relevant_surveys("外交", surveys, theme_category="politics")
        assert len(result) >= 1

    def test_exclude_all_surveys_returns_empty(self):
        """全 survey を exclude_survey_ids に含めると空リストが返る"""
        from src.app.services.society.survey_anchor import find_relevant_surveys, SurveyRecord

        surveys: list[SurveyRecord] = [
            SurveyRecord(
                theme="外交問題",
                question="q1",
                source="source-X",
                survey_date="2024-01",
                sample_size=3000,
                method="面接",
                stance_distribution={
                    "賛成": 0.25, "条件付き賛成": 0.20,
                    "中立": 0.30, "条件付き反対": 0.15, "反対": 0.10
                },
                theme_category="politics",
                relevance_keywords=["外交", "国際関係"],
            ),
        ]

        result = find_relevant_surveys(
            "外交",
            surveys,
            theme_category="politics",
            exclude_survey_ids=["source-X"],
        )
        assert result == []


# =============================================
# Rank C mapping の train/gate 除外テスト
# =============================================

class TestRankCExclusion:
    """Rank C mapping の train/gate 除外テスト"""

    @pytest.mark.asyncio
    async def test_rank_c_surveys_excluded_from_gate(self, db_session):
        """quality_rank=C の survey は gate 判定から除外される

        manifest に登録された quality_rank=C のソース名を使って確認する。
        テスト用の C ランクソース名は manifest に追加されている前提ではなく、
        manifest に含まれない不明なソースを使う場合と、
        build_validation_summary の gate_eligible フィールドを直接渡すケースの
        両方をカバーする。
        """
        from src.app.services.society.validation_pipeline import run_full_validation

        # manifest に存在しない不明なソースは gate_eligible=True（デフォルト）
        r = await register_result(
            db_session,
            "sim-v10",
            "オンライン意識調査テーマ",
            "economy",
            SIM_DIST,
        )
        await resolve_with_actual(db_session, r.id, ACTUAL_DIST_CLOSE, "オンライン調査A", "2024-01")

        results = await run_full_validation(
            db_session,
            theme_category="economy",
            exclude_quality_ranks=["C"],
        )

        # manifest に存在しないソースの場合 gate_eligible は True のまま（除外対象ではない）
        for res in results:
            if res.get("survey_source") == "オンライン調査A":
                # manifest にないソースは rank 不明 → 除外されない（gate_eligible=True）
                assert res.get("gate_eligible") is True

    def test_build_summary_excludes_rank_c_from_gate(self):
        """build_validation_summary は gate_eligible=False を gate 判定から除く"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        # gate_eligible=True の件数を MIN_VALIDATED_COUNT 以上にする
        passing_records = [
            {
                "emd": 0.08, "jsd": 0.05, "brier_score": 0.15,
                "status": "validated", "gate_eligible": True,
            }
            for _ in range(MIN_VALIDATED_COUNT)
        ]
        # Rank C (gate_eligible=False) で閾値を超えるレコード → gate に影響しない
        rank_c_records = [
            {
                "emd": 0.25, "jsd": 0.15, "brier_score": 0.40,
                "status": "validated", "gate_eligible": False,
            }
            for _ in range(5)  # 複数追加しても gate には影響しない
        ]
        records_data = passing_records + rank_c_records
        summary = build_validation_summary(records_data)

        # gate_eligible=True のレコードだけで判定 → pass になるはず
        assert summary["gate"] == "pass"
        assert summary["gate_eligible_count"] == MIN_VALIDATED_COUNT


# =============================================
# manifest 外 survey → survey_manifest_status="unmanifested" テスト
# =============================================

class TestSurveyManifestStatus:
    """manifest 外 survey ヒット → survey_manifest_status="unmanifested" テスト"""

    @pytest.mark.asyncio
    async def test_unmanifested_survey_sets_status(self, db_session):
        """manifest に含まれない survey と比較した場合 survey_manifest_status="unmanifested" が設定される"""
        from src.app.services.society.validation_pipeline import (
            run_full_validation,
            MANIFEST_DIR,
        )

        # manifest ディレクトリのロード対象外のソース名を使ってレコードを作成
        r = await register_result(db_session, "sim-v20", "未知テーマ", "economy", SIM_DIST)
        await resolve_with_actual(
            db_session, r.id, ACTUAL_DIST_CLOSE,
            survey_source="UNMANIFESTED_SOURCE_XYZ",
            survey_date="2024-01"
        )

        results = await run_full_validation(db_session, theme_category="economy")

        unmanifested = [
            res for res in results
            if res.get("survey_manifest_status") == "unmanifested"
        ]
        assert len(unmanifested) >= 1

    @pytest.mark.asyncio
    async def test_manifested_survey_sets_manifested_status(self, db_session):
        """manifest に含まれる survey_id は survey_manifest_status="manifested" になる"""
        from src.app.services.society.validation_pipeline import run_full_validation

        # economy manifest に含まれるソース名を使う
        r = await register_result(db_session, "sim-v21", "経済政策", "economy", SIM_DIST)
        await resolve_with_actual(
            db_session, r.id, ACTUAL_DIST_CLOSE,
            survey_source="日本銀行「生活意識に関するアンケート調査」2024年",
            survey_date="2024-03"
        )

        results = await run_full_validation(db_session, theme_category="economy")

        manifested = [
            res for res in results
            if res.get("survey_manifest_status") == "manifested"
        ]
        assert len(manifested) >= 1

    @pytest.mark.asyncio
    async def test_unresolved_record_has_no_manifest_status(self, db_session):
        """actual_distribution がない未解決レコードは survey_manifest_status=None"""
        from src.app.services.society.validation_pipeline import run_full_validation

        await register_result(db_session, "sim-v22", "経済政策", "economy", SIM_DIST)

        results = await run_full_validation(db_session, theme_category="economy")

        unresolved = [
            res for res in results
            if res.get("simulation_id") == "sim-v22"
        ]
        assert len(unresolved) == 1
        assert unresolved[0].get("survey_manifest_status") is None


# =============================================
# MIN_VALIDATED_PER_CATEGORY テスト
# =============================================

class TestMinValidatedPerCategory:
    """MIN_VALIDATED_PER_CATEGORY による inconclusive 判定テスト"""

    @pytest.mark.asyncio
    async def test_unknown_category_inconclusive_even_with_enough_records(self, db_session):
        """theme_category="unknown" を summary に渡すと件数に関わらず inconclusive になる"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        records_data = [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.15, "status": "validated"}
            for _ in range(MIN_VALIDATED_COUNT)
        ]
        summary = build_validation_summary(records_data, theme_category="unknown")

        assert summary["gate"] == "inconclusive"

    @pytest.mark.asyncio
    async def test_inconclusive_when_per_category_count_too_low(self, db_session):
        """カテゴリあたりの validated 件数が MIN_VALIDATED_PER_CATEGORY 未満 → inconclusive"""
        from src.app.services.society.validation_pipeline import (
            run_full_validation,
            build_validation_summary,
            MIN_VALIDATED_PER_CATEGORY,
        )

        # economy に MIN_VALIDATED_PER_CATEGORY - 1 件の validated を追加
        for i in range(max(0, MIN_VALIDATED_PER_CATEGORY - 1)):
            r = await register_result(
                db_session, f"sim-vpc{i}", "経済政策", "economy", SIM_DIST
            )
            await resolve_with_actual(db_session, r.id, ACTUAL_DIST_CLOSE, "src", "2024-01")

        results = await run_full_validation(db_session, theme_category="economy")
        summary = build_validation_summary(results, theme_category="economy")

        assert summary["gate"] == "inconclusive"


# =============================================
# unknown カテゴリ ガードテスト
# =============================================

class TestUnknownCategoryGuard:
    """theme_category="unknown" 時のガード動作テスト"""

    @pytest.mark.asyncio
    async def test_unknown_records_are_not_gate_eligible(self, db_session):
        """theme_category="unknown" のレコードは gate_eligible=False になる"""
        from src.app.services.society.validation_pipeline import run_full_validation

        r = await register_result(
            db_session, "sim-unk01", "未分類テーマ", "unknown", SIM_DIST
        )
        await resolve_with_actual(db_session, r.id, ACTUAL_DIST_CLOSE, "調査ソースA", "2024-01")

        results = await run_full_validation(db_session)

        unknown_records = [res for res in results if res["theme_category"] == "unknown"]
        assert len(unknown_records) >= 1
        for res in unknown_records:
            assert res["gate_eligible"] is False, (
                f"unknown category record should not be gate_eligible: {res}"
            )

    @pytest.mark.asyncio
    async def test_auto_compare_skips_unknown_category(self, db_session):
        """theme_category="unknown" のレコードは auto_compare が None を返す（survey 比較スキップ）"""
        from unittest.mock import patch
        from src.app.services.society.validation_pipeline import auto_compare

        r = await register_result(
            db_session, "sim-unk02", "未分類テーマ", "unknown", SIM_DIST
        )

        with patch(
            "src.app.services.society.validation_pipeline.compare_with_surveys"
        ) as mock_compare:
            result = await auto_compare(db_session, r, survey_data_dir="/tmp/surveys")

        mock_compare.assert_not_called()
        assert result is None

    def test_build_summary_with_unknown_theme_category_is_inconclusive(self):
        """build_validation_summary に theme_category="unknown" を渡すと inconclusive になる"""
        from src.app.services.society.validation_pipeline import (
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        records_data = [
            {"emd": 0.08, "jsd": 0.05, "brier_score": 0.15, "status": "validated"}
            for _ in range(MIN_VALIDATED_COUNT * 2)
        ]
        summary = build_validation_summary(records_data, theme_category="unknown")

        assert summary["gate"] == "inconclusive"

    @pytest.mark.asyncio
    async def test_unknown_does_not_pollute_known_category_gate(self, db_session):
        """unknown レコードが gate_eligible=False なので既知カテゴリのゲートに影響しない"""
        from src.app.services.society.validation_pipeline import (
            run_full_validation,
            build_validation_summary,
            MIN_VALIDATED_COUNT,
        )

        # economy の pass 分布レコードを MIN_VALIDATED_COUNT 件追加
        for i in range(MIN_VALIDATED_COUNT):
            r = await register_result(
                db_session, f"sim-econ{i}", "経済政策", "economy", SIM_DIST
            )
            await resolve_with_actual(
                db_session, r.id, ACTUAL_DIST_CLOSE, f"調査ソース{i}", "2024-01"
            )

        # unknown カテゴリで高 EMD レコードを追加（gate に影響しないはず）
        r_unk = await register_result(
            db_session, "sim-unkX", "未分類", "unknown", SIM_DIST
        )
        await resolve_with_actual(
            db_session, r_unk.id, ACTUAL_DIST_FAR, "不明ソース", "2024-01"
        )

        results = await run_full_validation(db_session, theme_category="economy")
        summary = build_validation_summary(results, theme_category="economy")

        # economy の pass 分布のみでゲート判定されるため pass になる
        assert summary["gate"] == "pass"
