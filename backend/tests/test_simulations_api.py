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


async def _seed_meta_simulation(session_factory) -> dict[str, str]:
    project_id = str(uuid.uuid4())
    sim_id = str(uuid.uuid4())

    async with session_factory() as session:
        project = Project(id=project_id, name="Meta Simulation", prompt_text="新規プロダクトの市場投入")
        simulation = Simulation(
            id=sim_id,
            project_id=project_id,
            mode="meta_simulation",
            prompt_text="新規プロダクトの市場投入",
            template_name="scenario_exploration",
            execution_profile="standard",
            status="completed",
            metadata_json={
                "run_config": {"evidence_mode": "strict", "trust_mode": "strict"},
                "meta_state": {
                    "current_cycle": 2,
                    "best_cycle_index": 2,
                    "best_score": 0.81,
                    "target_score": 0.78,
                    "stop_reason": "target_reached",
                },
                "meta_simulation_result": {
                    "type": "meta_simulation",
                    "content": "# Meta Simulation\n\n2回目の介入で市場受容が改善した。",
                    "summary_markdown": "# Meta Simulation\n\n2回目の介入で市場受容が改善した。",
                    "baseline": {
                        "world_run_id": str(uuid.uuid4()),
                        "world_summary": "価格受容性とブランド信頼が主要論点。",
                        "entity_count": 8,
                        "relation_count": 6,
                        "population_id": str(uuid.uuid4()),
                    },
                    "cycles": [
                        {
                            "cycle_index": 1,
                            "population_id": "pop-1",
                            "population_count": 1000,
                            "selected_count": 100,
                            "aggregation": {"average_confidence": 0.64},
                            "evaluation": {"consistency": 0.58, "calibration": 0.61},
                            "meeting": {"summary": "価格訴求の不明瞭さが対立点。"},
                            "issue_candidates": [
                                {
                                    "issue_id": "issue-1",
                                    "label": "価格受容性",
                                    "description": "価格に関する論点",
                                    "population_share": 0.42,
                                    "controversy_score": 0.51,
                                    "market_impact_score": 0.88,
                                    "network_spread_score": 0.66,
                                    "selection_score": 0.8,
                                }
                            ],
                            "selected_issues": [
                                {
                                    "issue_id": "issue-1",
                                    "label": "価格受容性",
                                    "description": "価格に関する論点",
                                    "population_share": 0.42,
                                    "controversy_score": 0.51,
                                    "market_impact_score": 0.88,
                                    "network_spread_score": 0.66,
                                    "selection_score": 0.8,
                                }
                            ],
                            "issue_colonies": [],
                            "scenarios": [
                                {
                                    "description": "[価格受容性] 価格障壁で導入が遅れる",
                                    "scenario_score": 0.68,
                                    "support_ratio": 0.55,
                                    "model_confidence_mean": 0.63,
                                    "ci": [0.48, 0.79],
                                    "supporting_colonies": 2,
                                    "total_colonies": 5,
                                    "claim_count": 4,
                                }
                            ],
                            "pm_board": {
                                "type": "pm_board",
                                "sections": {"top_5_actions": [{"action": "価格訴求を再設計する", "confidence": 0.72}]},
                                "overall_confidence": 0.7,
                            },
                            "interventions": [
                                {
                                    "intervention_id": "pm-1",
                                    "label": "価格訴求を再設計する",
                                    "change_type": "message",
                                    "hypothesis": "価格への不安を減らす",
                                    "target_issues": ["価格受容性"],
                                    "expected_effect": "高",
                                    "expected_delta": 0.74,
                                    "confidence": 0.72,
                                    "implementation_cost": "medium",
                                    "selection_score": 0.73,
                                }
                            ],
                            "selected_intervention": {
                                "intervention_id": "pm-1",
                                "label": "価格訴求を再設計する",
                                "change_type": "message",
                                "hypothesis": "価格への不安を減らす",
                                "target_issues": ["価格受容性"],
                                "expected_effect": "高",
                                "expected_delta": 0.74,
                                "confidence": 0.72,
                                "implementation_cost": "medium",
                                "selection_score": 0.73,
                            },
                            "score_breakdown": {
                                "society_score": 0.61,
                                "swarm_score": 0.68,
                                "pm_score": 0.7,
                                "objective_score": 0.66,
                            },
                            "objective_score": 0.66,
                            "stop_evaluation": {"reason": "continue"},
                        },
                        {
                            "cycle_index": 2,
                            "population_id": "pop-1",
                            "population_count": 1000,
                            "selected_count": 100,
                            "aggregation": {"average_confidence": 0.78},
                            "evaluation": {"consistency": 0.74, "calibration": 0.76},
                            "meeting": {"summary": "価格訴求変更で反発が緩和。"},
                            "issue_candidates": [
                                {
                                    "issue_id": "issue-1",
                                    "label": "価格受容性",
                                    "description": "価格に関する論点",
                                    "population_share": 0.35,
                                    "controversy_score": 0.43,
                                    "market_impact_score": 0.79,
                                    "network_spread_score": 0.62,
                                    "selection_score": 0.71,
                                }
                            ],
                            "selected_issues": [
                                {
                                    "issue_id": "issue-1",
                                    "label": "価格受容性",
                                    "description": "価格に関する論点",
                                    "population_share": 0.35,
                                    "controversy_score": 0.43,
                                    "market_impact_score": 0.79,
                                    "network_spread_score": 0.62,
                                    "selection_score": 0.71,
                                }
                            ],
                            "issue_colonies": [],
                            "scenarios": [
                                {
                                    "description": "[価格受容性] 価格変更で初期採用が回復する",
                                    "scenario_score": 0.81,
                                    "support_ratio": 0.71,
                                    "model_confidence_mean": 0.78,
                                    "ci": [0.62, 0.88],
                                    "supporting_colonies": 4,
                                    "total_colonies": 5,
                                    "claim_count": 7,
                                }
                            ],
                            "pm_board": {
                                "type": "pm_board",
                                "sections": {"top_5_actions": [{"action": "価格訴求を再設計する", "confidence": 0.81}]},
                                "overall_confidence": 0.82,
                            },
                            "interventions": [
                                {
                                    "intervention_id": "pm-1",
                                    "label": "価格訴求を再設計する",
                                    "change_type": "message",
                                    "hypothesis": "価格への不安を減らす",
                                    "target_issues": ["価格受容性"],
                                    "expected_effect": "高",
                                    "expected_delta": 0.81,
                                    "confidence": 0.81,
                                    "implementation_cost": "medium",
                                    "selection_score": 0.8,
                                }
                            ],
                            "selected_intervention": {
                                "intervention_id": "pm-1",
                                "label": "価格訴求を再設計する",
                                "change_type": "message",
                                "hypothesis": "価格への不安を減らす",
                                "target_issues": ["価格受容性"],
                                "expected_effect": "高",
                                "expected_delta": 0.81,
                                "confidence": 0.81,
                                "implementation_cost": "medium",
                                "selection_score": 0.8,
                            },
                            "score_breakdown": {
                                "society_score": 0.76,
                                "swarm_score": 0.81,
                                "pm_score": 0.82,
                                "objective_score": 0.81,
                            },
                            "objective_score": 0.81,
                            "stop_evaluation": {"reason": "target_reached"},
                        },
                    ],
                    "final_state": {
                        "best_cycle_index": 2,
                        "best_objective_score": 0.81,
                        "stop_reason": "target_reached",
                        "selected_intervention": {
                            "intervention_id": "pm-1",
                            "label": "価格訴求を再設計する",
                            "change_type": "message",
                            "hypothesis": "価格への不安を減らす",
                            "target_issues": ["価格受容性"],
                        },
                    },
                    "intervention_history": [
                        {
                            "intervention_id": "pm-1",
                            "label": "価格訴求を再設計する",
                            "change_type": "message",
                            "hypothesis": "価格への不安を減らす",
                            "target_issues": ["価格受容性"],
                            "expected_effect": "高",
                            "expected_delta": 0.81,
                            "confidence": 0.81,
                            "implementation_cost": "medium",
                        }
                    ],
                    "scenarios": [
                        {
                            "description": "[価格受容性] 価格変更で初期採用が回復する",
                            "scenario_score": 0.81,
                            "support_ratio": 0.71,
                            "model_confidence_mean": 0.78,
                            "ci": [0.62, 0.88],
                            "supporting_colonies": 4,
                            "total_colonies": 5,
                            "claim_count": 7,
                        }
                    ],
                    "pm_board": {
                        "type": "pm_board",
                        "sections": {"top_5_actions": [{"action": "価格訴求を再設計する", "confidence": 0.81}]},
                        "overall_confidence": 0.82,
                    },
                    "society_summary": {
                        "population_id": "pop-1",
                        "population_count": 1000,
                        "selected_count": 100,
                        "aggregation": {"average_confidence": 0.78},
                        "evaluation": {"consistency": 0.74, "calibration": 0.76},
                        "meeting": {"summary": "価格訴求変更で反発が緩和。"},
                    },
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
    assert payload["decision_brief"]["recommendation"] in {"Go", "条件付きGo", "No-Go"}
    assert payload["decision_brief"]["decision_summary"]
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
async def test_get_meta_simulation_report_returns_meta_payload(client, session_factory):
    seeded = await _seed_meta_simulation(session_factory)

    response = await client.get(f"/simulations/{seeded['simulation_id']}/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "meta_simulation"
    assert payload["final_state"]["best_cycle_index"] == 2
    assert payload["cycles"][1]["selected_intervention"]["label"] == "価格訴求を再設計する"
    assert payload["scenarios"][0]["description"].startswith("[価格受容性]")
    assert payload["quality"]["status"] == "unsupported"


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


@pytest.mark.asyncio
async def test_create_simulation_accepts_meta_mode(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(type(settings), "live_simulation_available", lambda self: True)
    monkeypatch.setattr("src.app.api.routes.simulations._spawn_simulation", lambda simulation_id: None)

    response = await client.post(
        "/simulations",
        json={
            "template_name": "scenario_exploration",
            "execution_profile": "standard",
            "mode": "meta_simulation",
            "prompt_text": "新規プロダクトの市場投入",
            "evidence_mode": "strict",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "meta_simulation"

    async with session_factory() as session:
        simulation = await session.get(Simulation, payload["id"])
        assert simulation is not None
        assert simulation.mode == "meta_simulation"


@pytest.mark.asyncio
async def test_create_simulation_accepts_unified_mode(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(type(settings), "live_simulation_available", lambda self: True)
    monkeypatch.setattr("src.app.api.routes.simulations._spawn_simulation", lambda simulation_id: None)

    response = await client.post(
        "/simulations",
        json={
            "template_name": "",
            "execution_profile": "standard",
            "mode": "unified",
            "prompt_text": "育児休暇の男性取得義務化",
            "evidence_mode": "prefer",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "unified"

    async with session_factory() as session:
        simulation = await session.get(Simulation, payload["id"])
        assert simulation is not None
        assert simulation.mode == "unified"


async def _seed_unified_simulation(session_factory) -> dict[str, str]:
    project_id = str(uuid.uuid4())
    sim_id = str(uuid.uuid4())

    async with session_factory() as session:
        project = Project(id=project_id, name="Unified Sim", prompt_text="育児休暇の男性取得義務化")
        simulation = Simulation(
            id=sim_id,
            project_id=project_id,
            mode="unified",
            prompt_text="育児休暇の男性取得義務化",
            template_name="",
            execution_profile="standard",
            status="completed",
            metadata_json={
                "run_config": {"evidence_mode": "prefer", "trust_mode": "strict"},
                "unified_result": {
                    "type": "unified",
                    "decision_brief": {
                        "recommendation": "条件付きGo",
                        "agreement_score": 0.72,
                        "agreement_breakdown": {"society": 0.78, "council": 0.68, "synthesis": 0.71},
                        "options": [
                            {"label": "段階的導入", "expected_effect": "+20%取得率", "risk": "中小企業の負担増"},
                        ],
                        "strongest_counterargument": "中小企業の人員不足が深刻化する可能性",
                        "risk_factors": [{"condition": "経済低迷", "impact": "企業の反発拡大"}],
                        "next_steps": ["中小企業向け支援策の検討", "パイロット地域の選定"],
                        "time_horizon": {
                            "short_term": {"period": "3ヶ月", "prediction": "制度設計開始"},
                            "mid_term": {"period": "1年", "prediction": "パイロット導入"},
                            "long_term": {"period": "3年", "prediction": "全国展開"},
                        },
                        "stakeholder_reactions": [
                            {"group": "子育て世帯", "reaction": "強い支持", "percentage": 89},
                            {"group": "中小企業経営者", "reaction": "懸念あり", "percentage": 42},
                        ],
                    },
                    "agreement_score": 0.72,
                    "content": "# 統合シミュレーションレポート\n\n## Decision Brief\n\n...",
                    "sections": {
                        "decision_brief": {"recommendation": "条件付きGo"},
                    },
                    "society_summary": {
                        "aggregation": {
                            "average_confidence": 0.78,
                            "stance_distribution": {"賛成": 0.55, "反対": 0.25, "中立": 0.2},
                        },
                    },
                    "council": {
                        "participants": [
                            {"display_name": "田中太郎（営業・45歳・東京）", "role": "citizen_representative"},
                        ],
                        "rounds": [[{"argument": "育休義務化は出生率向上に寄与"}]],
                        "synthesis": {"consensus_points": ["段階的導入が望ましい"]},
                        "devil_advocate_summary": "中小企業の負担が懸念",
                    },
                },
            },
        )
        session.add_all([project, simulation])
        await session.commit()

    return {"simulation_id": sim_id, "project_id": project_id}


@pytest.mark.asyncio
async def test_get_unified_report_returns_decision_brief(client, session_factory):
    seeded = await _seed_unified_simulation(session_factory)

    response = await client.get(f"/simulations/{seeded['simulation_id']}/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "unified"
    assert payload["decision_brief"]["recommendation"] == "条件付きGo"
    assert payload["agreement_score"] == 0.72
    assert payload["council"]["devil_advocate_summary"] == "中小企業の負担が懸念"
    assert payload["society_summary"]["aggregation"]["average_confidence"] == 0.78
