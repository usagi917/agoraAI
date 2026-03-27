"""LLMCallLog, ExperimentConfig 新モデルのテスト"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone


class TestLLMCallLog:
    @pytest.mark.asyncio
    async def test_create_minimal(self, db_session):
        from src.app.models.llm_call_log import LLMCallLog
        log = LLMCallLog(
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
        db_session.add(log)
        await db_session.commit()

        fetched = await db_session.get(LLMCallLog, log.id)
        assert fetched is not None
        assert fetched.task_name == "world_build"
        assert fetched.total_tokens == 150

    @pytest.mark.asyncio
    async def test_create_full_fields(self, db_session):
        from src.app.models.llm_call_log import LLMCallLog
        log = LLMCallLog(
            simulation_id="sim-2",
            task_name="entity_extract",
            provider="anthropic",
            model="claude-sonnet-4-6",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            latency_ms=2500,
            temperature=0.0,
            seed=42,
            system_prompt_hash="abc123",
            user_prompt_hash="def456",
            response_hash="ghi789",
            full_prompt="テスト用プロンプト",
            full_response="テスト用レスポンス",
        )
        db_session.add(log)
        await db_session.commit()

        fetched = await db_session.get(LLMCallLog, log.id)
        assert fetched.seed == 42
        assert fetched.full_prompt == "テスト用プロンプト"

    @pytest.mark.asyncio
    async def test_query_by_simulation_id(self, db_session):
        from src.app.models.llm_call_log import LLMCallLog
        from sqlalchemy import select

        for i in range(3):
            db_session.add(LLMCallLog(
                simulation_id="sim-q",
                task_name=f"task_{i}",
                provider="openai",
                model="gpt-4o",
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                latency_ms=100,
                temperature=0.5,
            ))
        db_session.add(LLMCallLog(
            simulation_id="sim-other",
            task_name="other",
            provider="openai",
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
            latency_ms=100,
            temperature=0.5,
        ))
        await db_session.commit()

        stmt = select(LLMCallLog).where(LLMCallLog.simulation_id == "sim-q")
        result = await db_session.execute(stmt)
        logs = result.scalars().all()
        assert len(logs) == 3

    @pytest.mark.asyncio
    async def test_latency_ms_is_positive(self, db_session):
        from src.app.models.llm_call_log import LLMCallLog
        log = LLMCallLog(
            simulation_id="sim-lat",
            task_name="test",
            provider="openai",
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
            latency_ms=500,
            temperature=0.5,
        )
        db_session.add(log)
        await db_session.commit()

        fetched = await db_session.get(LLMCallLog, log.id)
        assert fetched.latency_ms > 0


class TestExperimentConfig:
    @pytest.mark.asyncio
    async def test_create_snapshot(self, db_session):
        from src.app.models.experiment_config import ExperimentConfig
        config = ExperimentConfig(
            simulation_id="sim-cfg",
            models_yaml={"world_build": {"model": "gpt-4o"}},
            cognitive_yaml={"bdi": {"max_intentions": 3}},
            graphrag_yaml={"chunk_size": 500},
            llm_providers_yaml={"openai": {"api_key": "***"}},
            python_packages={"fastapi": "0.115.0", "sqlalchemy": "2.0.0"},
        )
        db_session.add(config)
        await db_session.commit()

        fetched = await db_session.get(ExperimentConfig, config.id)
        assert fetched is not None
        assert fetched.simulation_id == "sim-cfg"

    @pytest.mark.asyncio
    async def test_yaml_configs_serialized(self, db_session):
        from src.app.models.experiment_config import ExperimentConfig
        config = ExperimentConfig(
            simulation_id="sim-yaml",
            models_yaml={"key": "value"},
            cognitive_yaml={"bdi": True},
            graphrag_yaml={"chunk": 300},
            llm_providers_yaml={"provider": "openai"},
            python_packages={},
        )
        db_session.add(config)
        await db_session.commit()

        fetched = await db_session.get(ExperimentConfig, config.id)
        assert fetched.models_yaml == {"key": "value"}
        assert fetched.cognitive_yaml == {"bdi": True}
        assert fetched.graphrag_yaml == {"chunk": 300}

    @pytest.mark.asyncio
    async def test_package_versions_recorded(self, db_session):
        from src.app.models.experiment_config import ExperimentConfig
        packages = {"fastapi": "0.115.0", "numpy": "1.26.0", "litellm": "1.50.0"}
        config = ExperimentConfig(
            simulation_id="sim-pkg",
            models_yaml={},
            cognitive_yaml={},
            graphrag_yaml={},
            llm_providers_yaml={},
            python_packages=packages,
        )
        db_session.add(config)
        await db_session.commit()

        fetched = await db_session.get(ExperimentConfig, config.id)
        assert fetched.python_packages["fastapi"] == "0.115.0"
        assert len(fetched.python_packages) == 3

    @pytest.mark.asyncio
    async def test_git_commit_hash(self, db_session):
        from src.app.models.experiment_config import ExperimentConfig
        config = ExperimentConfig(
            simulation_id="sim-git",
            models_yaml={},
            cognitive_yaml={},
            graphrag_yaml={},
            llm_providers_yaml={},
            python_packages={},
            git_commit_hash="abc123def456",
        )
        db_session.add(config)
        await db_session.commit()

        fetched = await db_session.get(ExperimentConfig, config.id)
        assert fetched.git_commit_hash == "abc123def456"


class TestSimulationNewFields:
    @pytest.mark.asyncio
    async def test_seed_field(self, db_session):
        from src.app.models.simulation import Simulation
        sim = Simulation(
            mode="standard",
            prompt_text="test",
            template_name="general",
            execution_profile="preview",
            seed=42,
        )
        db_session.add(sim)
        await db_session.commit()

        fetched = await db_session.get(Simulation, sim.id)
        assert fetched.seed == 42

    @pytest.mark.asyncio
    async def test_seed_default_none(self, db_session):
        from src.app.models.simulation import Simulation
        sim = Simulation(
            mode="standard",
            prompt_text="test",
            template_name="general",
            execution_profile="preview",
        )
        db_session.add(sim)
        await db_session.commit()

        fetched = await db_session.get(Simulation, sim.id)
        assert fetched.seed is None
