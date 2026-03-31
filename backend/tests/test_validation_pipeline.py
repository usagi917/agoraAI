"""ValidationRecord モデル・リポジトリ・パイプラインのテスト

Phase 4: DB モデルとリポジトリ
Phase 5: 検証パイプライン
"""

import os
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from src.app.database import Base

# 全モデルを import して Base.metadata に登録する
import src.app.models  # noqa: F401

from src.app.models.validation_record import ValidationRecord
from src.app.repositories.validation_repo import ValidationRepository
from src.app.services.society.validation_pipeline import (
    register_result,
    auto_compare,
    resolve_with_actual,
    generate_accuracy_report,
    update_bias_profile,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


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


SIM_DIST = {"賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.10}
ACTUAL_DIST = {"賛成": 0.25, "条件付き賛成": 0.20, "中立": 0.25, "条件付き反対": 0.15, "反対": 0.15}


class TestValidationRecordModel:
    @pytest.mark.asyncio
    async def test_create_validation_record(self, db_session):
        """ValidationRecord を作成し DB に保存、再取得できる"""
        repo = ValidationRepository(db_session)
        record = await repo.save(
            simulation_id="sim-001",
            theme_text="外交問題",
            theme_category="politics",
            simulated_distribution=SIM_DIST,
        )
        assert record.id is not None
        retrieved = await repo.get(record.id)
        assert retrieved is not None
        assert retrieved.theme_text == "外交問題"

    @pytest.mark.asyncio
    async def test_record_fields_persisted(self, db_session):
        """全フィールドが正しく永続化"""
        repo = ValidationRepository(db_session)
        record = await repo.save(
            simulation_id="sim-002",
            theme_text="防衛政策",
            theme_category="security",
            simulated_distribution=SIM_DIST,
            calibrated_distribution=ACTUAL_DIST,
        )
        retrieved = await repo.get(record.id)
        assert retrieved.simulation_id == "sim-002"
        assert retrieved.theme_category == "security"
        assert retrieved.simulated_distribution == SIM_DIST
        assert retrieved.calibrated_distribution == ACTUAL_DIST

    @pytest.mark.asyncio
    async def test_record_with_pending_actual(self, db_session):
        """actual_distribution=None で作成、validated_at=None"""
        repo = ValidationRepository(db_session)
        record = await repo.save(
            simulation_id="sim-003",
            theme_text="経済政策",
            theme_category="economy",
            simulated_distribution=SIM_DIST,
        )
        assert record.actual_distribution is None
        assert record.validated_at is None

    @pytest.mark.asyncio
    async def test_resolve_validation_sets_actual(self, db_session):
        """resolve() で actual_distribution, survey_source, survey_date が設定される"""
        repo = ValidationRepository(db_session)
        record = await repo.save(
            simulation_id="sim-004",
            theme_text="外交問題",
            theme_category="politics",
            simulated_distribution=SIM_DIST,
        )
        resolved = await repo.resolve(
            record_id=record.id,
            actual_distribution=ACTUAL_DIST,
            survey_source="内閣府",
            survey_date="2024-01",
        )
        assert resolved.actual_distribution == ACTUAL_DIST
        assert resolved.survey_source == "内閣府"
        assert resolved.survey_date == "2024-01"

    @pytest.mark.asyncio
    async def test_resolve_validation_computes_brier(self, db_session):
        """resolve() で brier_score が自動算出される"""
        repo = ValidationRepository(db_session)
        record = await repo.save(
            simulation_id="sim-005",
            theme_text="test",
            theme_category="politics",
            simulated_distribution=SIM_DIST,
        )
        resolved = await repo.resolve(
            record.id, ACTUAL_DIST, "test", "2024-01"
        )
        assert resolved.brier_score is not None
        assert resolved.brier_score >= 0

    @pytest.mark.asyncio
    async def test_resolve_validation_computes_kl(self, db_session):
        """resolve() で kl_divergence が自動算出される"""
        repo = ValidationRepository(db_session)
        record = await repo.save(
            simulation_id="sim-006",
            theme_text="test",
            theme_category="politics",
            simulated_distribution=SIM_DIST,
        )
        resolved = await repo.resolve(
            record.id, ACTUAL_DIST, "test", "2024-01"
        )
        assert resolved.kl_divergence is not None
        assert resolved.kl_divergence >= 0

    @pytest.mark.asyncio
    async def test_resolve_validation_computes_emd(self, db_session):
        """resolve() で emd が自動算出される"""
        repo = ValidationRepository(db_session)
        record = await repo.save(
            simulation_id="sim-007",
            theme_text="test",
            theme_category="politics",
            simulated_distribution=SIM_DIST,
        )
        resolved = await repo.resolve(
            record.id, ACTUAL_DIST, "test", "2024-01"
        )
        assert resolved.emd is not None
        assert resolved.emd >= 0

    @pytest.mark.asyncio
    async def test_resolve_validation_sets_validated_at(self, db_session):
        """resolve() で validated_at がタイムスタンプ設定"""
        repo = ValidationRepository(db_session)
        record = await repo.save(
            simulation_id="sim-008",
            theme_text="test",
            theme_category="politics",
            simulated_distribution=SIM_DIST,
        )
        resolved = await repo.resolve(
            record.id, ACTUAL_DIST, "test", "2024-01"
        )
        assert resolved.validated_at is not None


class TestValidationRecordQueries:
    @pytest.mark.asyncio
    async def test_list_by_simulation(self, db_session):
        """simulation_id でフィルタリング"""
        repo = ValidationRepository(db_session)
        await repo.save("sim-A", "t1", "politics", SIM_DIST)
        await repo.save("sim-A", "t2", "economy", SIM_DIST)
        await repo.save("sim-B", "t3", "social", SIM_DIST)
        results = await repo.list_by_simulation("sim-A")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_by_category(self, db_session):
        """theme_category でフィルタリング"""
        repo = ValidationRepository(db_session)
        await repo.save("sim-C", "t1", "economy", SIM_DIST)
        await repo.save("sim-D", "t2", "economy", SIM_DIST)
        await repo.save("sim-E", "t3", "social", SIM_DIST)
        results = await repo.list_by_category("economy")
        assert len(results) == 2


class TestValidationRecordAggregation:
    @pytest.mark.asyncio
    async def test_aggregate_by_category(self, db_session):
        """カテゴリ別の平均 Brier/KL/EMD を算出"""
        repo = ValidationRepository(db_session)
        r1 = await repo.save("sim-F", "t1", "economy", SIM_DIST)
        await repo.resolve(r1.id, ACTUAL_DIST, "src", "2024-01")
        r2 = await repo.save("sim-G", "t2", "economy", SIM_DIST)
        await repo.resolve(r2.id, ACTUAL_DIST, "src", "2024-01")

        agg = await repo.aggregate_by_category("economy")
        assert "avg_brier" in agg
        assert "avg_kl" in agg
        assert "avg_emd" in agg
        assert agg["count"] == 2

    @pytest.mark.asyncio
    async def test_aggregate_by_category_excludes_unvalidated(self, db_session):
        """未検証レコードは集計から除外"""
        repo = ValidationRepository(db_session)
        r1 = await repo.save("sim-H", "t1", "social", SIM_DIST)
        await repo.resolve(r1.id, ACTUAL_DIST, "src", "2024-01")
        await repo.save("sim-I", "t2", "social", SIM_DIST)  # unresolved

        agg = await repo.aggregate_by_category("social")
        assert agg["count"] == 1


# ===== Phase 5: 検証パイプライン =====


class TestValidationPipeline:
    @pytest.mark.asyncio
    async def test_register_result(self, db_session):
        """シミュレーション結果から ValidationRecord を生成・保存"""
        record = await register_result(
            db_session,
            simulation_id="sim-P1",
            theme="外交問題",
            theme_category="politics",
            distribution=SIM_DIST,
        )
        assert record.id is not None
        assert record.theme_text == "外交問題"
        assert record.simulated_distribution == SIM_DIST

    @pytest.mark.asyncio
    async def test_register_result_with_calibrated(self, db_session):
        """calibrated_distribution 付きで登録"""
        record = await register_result(
            db_session,
            simulation_id="sim-P2",
            theme="防衛",
            theme_category="security",
            distribution=SIM_DIST,
            calibrated_distribution=ACTUAL_DIST,
        )
        assert record.calibrated_distribution == ACTUAL_DIST

    @pytest.mark.asyncio
    async def test_auto_compare_finds_relevant_survey(self, db_session):
        """関連する調査データと自動比較し ComparisonReport を返す"""
        record = await register_result(
            db_session, "sim-P3", "外交", "politics", SIM_DIST
        )
        report = await auto_compare(db_session, record, FIXTURES_DIR)
        assert report is not None
        assert "kl_divergence" in report
        assert "emd" in report

    @pytest.mark.asyncio
    async def test_auto_compare_no_relevant_survey(self, db_session, tmp_path):
        """関連調査なしで None を返す"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        record = await register_result(
            db_session, "sim-P4", "外交", "politics", SIM_DIST
        )
        report = await auto_compare(db_session, record, str(empty_dir))
        assert report is None

    @pytest.mark.asyncio
    async def test_resolve_with_actual(self, db_session):
        """実績データを投入し精度指標が計算される"""
        record = await register_result(
            db_session, "sim-P5", "test", "economy", SIM_DIST
        )
        resolved = await resolve_with_actual(
            db_session, record.id, ACTUAL_DIST, "内閣府", "2024-01"
        )
        assert resolved.actual_distribution == ACTUAL_DIST
        assert resolved.brier_score is not None
        assert resolved.kl_divergence is not None
        assert resolved.emd is not None

    @pytest.mark.asyncio
    async def test_generate_accuracy_report_empty(self, db_session):
        """検証済みレコードなしで空レポート"""
        report = await generate_accuracy_report(db_session)
        assert report["total_validated"] == 0

    @pytest.mark.asyncio
    async def test_generate_accuracy_report_with_data(self, db_session):
        """検証済みレコードありでカテゴリ別精度レポート"""
        r1 = await register_result(db_session, "sim-P6", "t1", "economy", SIM_DIST)
        await resolve_with_actual(db_session, r1.id, ACTUAL_DIST, "src", "2024-01")
        r2 = await register_result(db_session, "sim-P7", "t2", "economy", SIM_DIST)
        await resolve_with_actual(db_session, r2.id, ACTUAL_DIST, "src", "2024-01")

        report = await generate_accuracy_report(db_session, "economy")
        assert report["total_validated"] == 2
        assert "overall_brier" in report
        assert "overall_kl" in report
        assert "overall_emd" in report

    @pytest.mark.asyncio
    async def test_update_bias_profile(self, db_session):
        """蓄積された比較データからバイアスプロファイルを再構築"""
        r1 = await register_result(db_session, "sim-P8", "t1", "economy", SIM_DIST)
        await resolve_with_actual(db_session, r1.id, ACTUAL_DIST, "src", "2024-01")

        profile = await update_bias_profile(db_session, FIXTURES_DIR)
        # プロファイルが返される（データが1件しかないので中身はシンプル）
        assert isinstance(profile, dict)
