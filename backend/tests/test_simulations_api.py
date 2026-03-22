import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.api.deps import get_session
from src.app.config import settings
from src.app.database import Base
from src.app.main import app
from src.app.models import _import_all_models
from src.app.models.document import Document
from src.app.models.followup import Followup
from src.app.models.project import Project
from src.app.models.report import Report
from src.app.models.run import Run
from src.app.models.simulation import Simulation
from src.app.models.world_state import WorldState


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "simulations-api.db"
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

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client

    app.dependency_overrides.clear()


async def _seed_single_simulation(session_factory) -> dict[str, str]:
    project_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    sim_id = str(uuid.uuid4())

    async with session_factory() as session:
        project = Project(id=project_id, name="Battery Analysis", prompt_text="battery regulation")
        run = Run(
            id=run_id,
            project_id=project_id,
            template_name="business_analysis",
            execution_profile="standard",
            status="completed",
        )
        simulation = Simulation(
            id=sim_id,
            project_id=project_id,
            mode="single",
            prompt_text="battery regulation",
            template_name="business_analysis",
            execution_profile="standard",
            run_id=run_id,
            status="completed",
            metadata_json={"run_config": {"evidence_mode": "required", "trust_mode": "strict"}},
        )
        document = Document(
            id=str(uuid.uuid4()),
            project_id=project_id,
            filename="market-notes.md",
            content_type="text/markdown",
            text_content=(
                "Battery chemistry costs remain volatile.\n\n"
                "Regulation risk is increasing because subsidy rules and local content "
                "requirements tighten in 2026.\n\n"
                "Manufacturing scale is still the main execution bottleneck."
            ),
            char_count=186,
        )
        report = Report(
            id=str(uuid.uuid4()),
            run_id=run_id,
            content="規制と供給網リスクが重要です。",
            sections={
                "summary": "規制と供給網リスクが重要です。",
                "quality": {
                    "status": "verified",
                    "fallback_used": False,
                    "fallback_reason": "",
                    "calibration_status": "uncalibrated",
                },
            },
            status="completed",
        )
        world_state = WorldState(
            id=str(uuid.uuid4()),
            run_id=run_id,
            round_number=1,
            state_data={"entities": [{"label": "Regulation", "importance_score": 0.8}]},
        )

        session.add_all([project, run, simulation, document, report, world_state])
        await session.commit()

    return {"simulation_id": sim_id, "project_id": project_id, "run_id": run_id}


async def _seed_prompt_only_simulation(session_factory, *, evidence_mode: str = "strict") -> dict[str, str]:
    project_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    sim_id = str(uuid.uuid4())

    async with session_factory() as session:
        project = Project(id=project_id, name="Prompt Only", prompt_text="market sizing prompt only")
        run = Run(
            id=run_id,
            project_id=project_id,
            template_name="business_analysis",
            execution_profile="standard",
            status="completed",
        )
        simulation = Simulation(
            id=sim_id,
            project_id=project_id,
            mode="single",
            prompt_text="market sizing prompt only",
            template_name="business_analysis",
            execution_profile="standard",
            run_id=run_id,
            status="completed",
            metadata_json={"run_config": {"evidence_mode": evidence_mode, "trust_mode": "strict"}},
        )
        report = Report(
            id=str(uuid.uuid4()),
            run_id=run_id,
            content="プロンプトのみから生成された要約です。",
            sections={"summary": "プロンプトのみから生成された要約です。"},
            status="completed",
        )
        session.add_all([project, run, simulation, report])
        await session.commit()

    return {"simulation_id": sim_id, "project_id": project_id, "run_id": run_id}


async def _seed_society_first_simulation(session_factory) -> dict[str, str]:
    project_id = str(uuid.uuid4())
    sim_id = str(uuid.uuid4())

    async with session_factory() as session:
        project = Project(id=project_id, name="Society First", prompt_text="新規サービス投入時の市場反応")
        simulation = Simulation(
            id=sim_id,
            project_id=project_id,
            mode="society_first",
            prompt_text="新規サービス投入時の市場反応",
            template_name="scenario_exploration",
            execution_profile="standard",
            status="completed",
            metadata_json={
                "run_config": {"evidence_mode": "strict", "trust_mode": "strict"},
                "society_first_result": {
                    "type": "society_first",
                    "content": "# Society First\n\n価格受容性が最大論点です。",
                    "sections": {},
                    "society_summary": {
                        "aggregation": {
                            "average_confidence": 0.71,
                            "stance_distribution": {"賛成": 0.45, "反対": 0.35, "中立": 0.2},
                        }
                    },
                    "issue_candidates": [
                        {
                            "issue_id": "issue-1",
                            "label": "価格受容性",
                            "description": "価格に関する論点",
                            "population_share": 0.4,
                            "controversy_score": 0.5,
                            "market_impact_score": 0.9,
                            "network_spread_score": 0.7,
                            "selection_score": 0.82,
                        }
                    ],
                    "selected_issues": [
                        {
                            "issue_id": "issue-1",
                            "label": "価格受容性",
                            "description": "価格に関する論点",
                            "population_share": 0.4,
                            "controversy_score": 0.5,
                            "market_impact_score": 0.9,
                            "network_spread_score": 0.7,
                            "selection_score": 0.82,
                        }
                    ],
                    "issue_colonies": [
                        {
                            "issue_id": "issue-1",
                            "label": "価格受容性",
                            "description": "価格に関する論点",
                            "integrated_report": "価格障壁で初期採用が鈍る。",
                            "top_scenarios": [
                                {
                                    "description": "価格障壁で導入が遅れる",
                                    "scenario_score": 0.73,
                                    "support_ratio": 0.6,
                                    "model_confidence_mean": 0.7,
                                    "ci": [0.52, 0.81],
                                    "supporting_colonies": 3,
                                    "total_colonies": 5,
                                    "claim_count": 6,
                                }
                            ],
                        }
                    ],
                    "intervention_comparison": [
                        {
                            "intervention_id": "price_reduction",
                            "label": "価格変更",
                            "change_summary": "初期費用を引き下げる",
                            "affected_issues": ["価格受容性"],
                            "expected_effect": "高",
                        }
                    ],
                    "scenarios": [
                        {
                            "description": "[価格受容性] 価格障壁で導入が遅れる",
                            "scenario_score": 0.73,
                            "support_ratio": 0.6,
                            "model_confidence_mean": 0.7,
                            "ci": [0.52, 0.81],
                            "supporting_colonies": 3,
                            "total_colonies": 5,
                            "claim_count": 6,
                        }
                    ],
                    "verification": {"status": "passed", "score": 1.0, "issues": [], "warnings": [], "metrics": {}},
                },
            },
        )
        session.add_all([project, simulation])
        await session.commit()

    return {"simulation_id": sim_id, "project_id": project_id}


@pytest.mark.asyncio
async def test_get_simulation_report_includes_quality_and_evidence_refs(client, session_factory):
    seeded = await _seed_single_simulation(session_factory)

    response = await client.get(f"/simulations/{seeded['simulation_id']}/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "single"
    assert payload["quality"]["status"] == "verified"
    assert payload["quality"]["trust_level"] == "high_trust"
    assert any(ref["source_type"] == "document_chunk" for ref in payload["evidence_refs"])
    assert all(ref["char_end"] > ref["char_start"] for ref in payload["evidence_refs"])


@pytest.mark.asyncio
async def test_get_simulation_report_marks_prompt_only_strict_runs_as_unsupported(client, session_factory):
    seeded = await _seed_prompt_only_simulation(session_factory, evidence_mode="strict")

    response = await client.get(f"/simulations/{seeded['simulation_id']}/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["quality"]["status"] == "unsupported"
    assert payload["quality"]["unsupported_reason"] == "strict_document_evidence_required"
    assert payload["run_config"]["evidence_mode"] == "strict"


@pytest.mark.asyncio
async def test_get_society_first_report_returns_issue_driven_payload(client, session_factory):
    seeded = await _seed_society_first_simulation(session_factory)

    response = await client.get(f"/simulations/{seeded['simulation_id']}/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "society_first"
    assert payload["issue_candidates"][0]["label"] == "価格受容性"
    assert payload["intervention_comparison"][0]["label"] == "価格変更"
    assert payload["scenarios"][0]["description"].startswith("[価格受容性]")
    assert payload["backtest"]["summary"]["case_count"] == 0


@pytest.mark.asyncio
async def test_create_society_first_backtest_updates_report_and_interventions(client, session_factory):
    seeded = await _seed_society_first_simulation(session_factory)

    response = await client.post(
        f"/simulations/{seeded['simulation_id']}/backtest",
        json={
            "historical_cases": [
                {
                    "title": "2025 関西ローンチ",
                    "observed_at": "2025-10-01",
                    "baseline_metrics": {
                        "adoption_rate": 0.18,
                        "conversion_rate": 0.09,
                    },
                    "outcome": {
                        "issue_label": "価格受容性",
                        "summary": "価格改定後も本格導入は遅れたが試験導入は増えた",
                        "actual_scenario": "価格障壁で導入が遅れる",
                        "metrics": {
                            "adoption_rate": 0.27,
                            "conversion_rate": 0.13,
                        },
                        "tags": ["価格", "導入"],
                    },
                    "interventions": [
                        {
                            "intervention_id": "price_reduction",
                            "label": "価格変更",
                            "baseline_metrics": {
                                "adoption_rate": 0.18,
                                "conversion_rate": 0.09,
                            },
                            "outcome_metrics": {
                                "adoption_rate": 0.27,
                                "conversion_rate": 0.13,
                            },
                            "evidence": ["初月の採用率が改善した"],
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["summary"]["hit_count"] == 1

    report_response = await client.get(f"/simulations/{seeded['simulation_id']}/report")
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert report_payload["backtest"]["summary"]["case_count"] == 1
    assert report_payload["intervention_comparison"][0]["comparison_mode"] == "observed"
    assert report_payload["intervention_comparison"][0]["observed_uplift"] > 0


@pytest.mark.asyncio
async def test_create_simulation_followup_returns_answer_and_relevant_evidence_refs(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    seeded = await _seed_single_simulation(session_factory)

    async def _fake_handle_followup(*args, **kwargs):
        return "規制変更の前提検証を先に進めるべきです。"

    monkeypatch.setattr(
        "src.app.api.routes.simulations.handle_followup",
        _fake_handle_followup,
    )

    response = await client.post(
        f"/simulations/{seeded['simulation_id']}/followups",
        params={"question": "regulation risk matters?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert "規制変更" in payload["answer"]
    assert payload["quality"]["trust_level"] == "high_trust"
    assert any(ref["source_type"] == "document_chunk" for ref in payload["evidence_refs"])

    async with session_factory() as session:
        stored = await session.get(Followup, payload["id"])
        assert stored is not None
        assert stored.status == "completed"


@pytest.mark.asyncio
async def test_create_simulation_normalizes_legacy_evidence_mode_alias(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(type(settings), "live_simulation_available", lambda self: True)
    monkeypatch.setattr("src.app.api.routes.simulations._spawn_simulation", lambda simulation_id: None)

    response = await client.post(
        "/simulations",
        json={
            "template_name": "business_analysis",
            "execution_profile": "standard",
            "mode": "single",
            "prompt_text": "battery regulation",
            "evidence_mode": "required",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence_mode"] == "strict"

    async with session_factory() as session:
        simulation = await session.get(Simulation, payload["id"])
        assert simulation is not None
        assert simulation.metadata_json["run_config"]["evidence_mode"] == "strict"
