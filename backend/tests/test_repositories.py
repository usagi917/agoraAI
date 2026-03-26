"""Repository レイヤーのテスト"""

import pytest
import pytest_asyncio

from tests.factories import make_simulation


class TestSimulationRepository:
    @pytest.mark.asyncio
    async def test_create(self, db_session):
        from src.app.repositories.simulation_repo import SimulationRepository
        repo = SimulationRepository(db_session)

        sim = await repo.create(
            mode="standard",
            prompt_text="テスト",
            template_name="general",
            execution_profile="preview",
        )
        assert sim.id is not None
        assert sim.mode == "standard"

    @pytest.mark.asyncio
    async def test_get_found(self, db_session):
        from src.app.repositories.simulation_repo import SimulationRepository
        repo = SimulationRepository(db_session)

        sim = await repo.create(mode="standard", prompt_text="test", template_name="g", execution_profile="preview")
        fetched = await repo.get(sim.id)
        assert fetched is not None
        assert fetched.id == sim.id

    @pytest.mark.asyncio
    async def test_get_not_found(self, db_session):
        from src.app.repositories.simulation_repo import SimulationRepository
        repo = SimulationRepository(db_session)
        fetched = await repo.get("nonexistent-id")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_list_ordered(self, db_session):
        from src.app.repositories.simulation_repo import SimulationRepository
        repo = SimulationRepository(db_session)

        await repo.create(mode="standard", prompt_text="first", template_name="g", execution_profile="preview")
        await repo.create(mode="deep", prompt_text="second", template_name="g", execution_profile="preview")

        sims = await repo.list()
        assert len(sims) == 2

    @pytest.mark.asyncio
    async def test_update_status(self, db_session):
        from src.app.repositories.simulation_repo import SimulationRepository
        repo = SimulationRepository(db_session)

        sim = await repo.create(mode="standard", prompt_text="test", template_name="g", execution_profile="preview")
        await repo.update_status(sim.id, "completed")

        fetched = await repo.get(sim.id)
        assert fetched.status == "completed"

    @pytest.mark.asyncio
    async def test_save_result(self, db_session):
        from src.app.repositories.simulation_repo import SimulationRepository
        repo = SimulationRepository(db_session)

        sim = await repo.create(mode="standard", prompt_text="test", template_name="g", execution_profile="preview")
        await repo.save_result(sim.id, {"unified_result": {"type": "standard"}})

        fetched = await repo.get(sim.id)
        assert fetched.metadata_json["unified_result"]["type"] == "standard"


class TestEvaluationRepository:
    @pytest.mark.asyncio
    async def test_save_metrics(self, db_session):
        from src.app.repositories.evaluation_repo import EvaluationRepository
        from src.app.repositories.simulation_repo import SimulationRepository

        sim_repo = SimulationRepository(db_session)
        sim = await sim_repo.create(mode="standard", prompt_text="t", template_name="g", execution_profile="preview")

        eval_repo = EvaluationRepository(db_session)
        await eval_repo.save_metrics(sim.id, [
            {"metric_name": "diversity", "score": 0.85, "details": {"entropy": 0.92}},
            {"metric_name": "consistency", "score": 0.72, "details": {}},
        ])

        metrics = await eval_repo.get_by_simulation(sim.id)
        assert len(metrics) == 2

    @pytest.mark.asyncio
    async def test_get_by_metric_name(self, db_session):
        from src.app.repositories.evaluation_repo import EvaluationRepository
        from src.app.repositories.simulation_repo import SimulationRepository

        sim_repo = SimulationRepository(db_session)
        sim = await sim_repo.create(mode="standard", prompt_text="t", template_name="g", execution_profile="preview")

        eval_repo = EvaluationRepository(db_session)
        await eval_repo.save_metrics(sim.id, [
            {"metric_name": "diversity", "score": 0.85, "details": {}},
            {"metric_name": "consistency", "score": 0.72, "details": {}},
        ])

        metrics = await eval_repo.get_by_metric_name(sim.id, "diversity")
        assert len(metrics) == 1
        assert metrics[0].score == 0.85


class TestLLMCallLogRepository:
    @pytest.mark.asyncio
    async def test_save_and_list(self, db_session):
        from src.app.repositories.llm_log_repo import LLMCallLogRepository

        repo = LLMCallLogRepository(db_session)
        await repo.log_call(
            simulation_id="sim-1",
            task_name="world_build",
            provider="openai",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=1200,
            temperature=0.5,
        )
        await repo.log_call(
            simulation_id="sim-1",
            task_name="entity_extract",
            provider="openai",
            model="gpt-4o",
            prompt_tokens=80,
            completion_tokens=40,
            total_tokens=120,
            latency_ms=900,
            temperature=0.5,
        )

        logs = await repo.get_by_simulation("sim-1")
        assert len(logs) == 2

    @pytest.mark.asyncio
    async def test_get_summary(self, db_session):
        from src.app.repositories.llm_log_repo import LLMCallLogRepository

        repo = LLMCallLogRepository(db_session)
        await repo.log_call(
            simulation_id="sim-s",
            task_name="t1",
            provider="openai",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=1200,
            temperature=0.5,
        )

        summary = await repo.get_summary("sim-s")
        assert summary["total_calls"] == 1
        assert summary["total_tokens"] == 150
