"""レポートAPI `/simulations/{id}/report` の契約(JSON形状)テスト。

各レポート形式(single / society_first / meta_simulation / unified)のトップレベル
キー集合を固定し、P5 の get_simulation_report 6分岐統合・repository 層導入で
キーの削除/改名が混入したら即検知できるようにする安全網。
値の詳細検証は test_simulations_api.py が担う。ここでは「形状」のみを契約とする。
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.api.deps import get_session
from src.app.database import Base
from src.app.main import app
from src.app.models import _import_all_models
from test_simulations_api import (
    _seed_single_simulation,
    _seed_society_first_simulation,
    _seed_meta_simulation,
    _seed_unified_simulation,
)

# 各形式の現行トップレベルキー集合(2026-06-29 時点の実レスポンスから取得)。
EXPECTED_REPORT_KEYS = {
    "single": {
        "content", "decision_brief", "evidence_refs", "id", "prediction_evaluations",
        "quality", "run_config", "run_id", "sections", "status", "type",
        "validation_summary", "verification",
    },
    "society_first": {
        "backtest", "content", "evidence_refs", "intervention_comparison",
        "issue_candidates", "issue_colonies", "prediction_evaluations", "quality",
        "run_config", "scenarios", "sections", "selected_issues", "society_summary",
        "type", "validation_summary", "verification",
    },
    "meta_simulation": {
        "baseline", "content", "cycles", "evidence_refs", "final_state",
        "intervention_history", "pm_board", "prediction_evaluations", "quality",
        "run_config", "scenarios", "society_summary", "summary_markdown", "type",
        "validation_summary",
    },
    "unified": {
        "agreement_score", "content", "council", "decision_brief", "evidence_refs",
        "prediction_evaluations", "quality", "run_config", "sections",
        "society_summary", "type", "validation_summary",
    },
}


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "report-contract.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    _import_all_models()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield session_maker
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "seeder, expected_type",
    [
        (_seed_single_simulation, "single"),
        (_seed_society_first_simulation, "society_first"),
        (_seed_meta_simulation, "meta_simulation"),
        (_seed_unified_simulation, "unified"),
    ],
)
async def test_report_top_level_shape_is_stable(client, session_factory, seeder, expected_type):
    seeded = await seeder(session_factory)

    response = await client.get(f"/simulations/{seeded['simulation_id']}/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == expected_type
    assert set(payload.keys()) == EXPECTED_REPORT_KEYS[expected_type], (
        f"{expected_type} レポートのトップレベルキー集合が変化した。"
        f"差分(追加/欠落): {set(payload.keys()) ^ EXPECTED_REPORT_KEYS[expected_type]}"
    )
    # 共通の構造不変条件
    assert isinstance(payload["quality"], dict)
    assert isinstance(payload["evidence_refs"], list)
    assert isinstance(payload["validation_summary"], dict)
    assert isinstance(payload["run_config"], dict)
