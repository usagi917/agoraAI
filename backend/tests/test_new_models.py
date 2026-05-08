"""ExperimentConfig と Simulation 追加フィールドのテスト"""

import pytest


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
