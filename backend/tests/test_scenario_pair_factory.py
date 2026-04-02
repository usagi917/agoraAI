"""Scenario Pair Factory のテスト (Stream C)"""

import pytest
from sqlalchemy import select

from src.app.models.population import Population
from src.app.models.scenario_pair import ScenarioPair
from src.app.models.simulation import Simulation
from src.app.services.scenario_pair_factory import create_scenario_pair


class TestCreateScenarioPair:
    @pytest.mark.asyncio
    async def test_create_scenario_pair(self, db_session):
        """ScenarioPair + 2 Simulations が作成されることを検証"""
        pop = Population(agent_count=500)
        db_session.add(pop)
        await db_session.commit()

        pair = await create_scenario_pair(
            session=db_session,
            population_id=pop.id,
            intervention_params={"policy_type": "subsidy", "amount": 1000},
            decision_context="Youth employment subsidy policy",
            preset="standard",
            seed=42,
        )

        assert pair is not None
        assert pair.id is not None

        # 2 simulations should exist
        stmt = select(Simulation).where(Simulation.scenario_pair_id == pair.id)
        result = await db_session.execute(stmt)
        sims = result.scalars().all()
        assert len(sims) == 2

    @pytest.mark.asyncio
    async def test_scenario_pair_links_simulations(self, db_session):
        """baseline_simulation_id と intervention_simulation_id が設定されることを検証"""
        pop = Population(agent_count=200)
        db_session.add(pop)
        await db_session.commit()

        pair = await create_scenario_pair(
            session=db_session,
            population_id=pop.id,
            intervention_params={"tax_rate": 0.15},
            decision_context="Tax policy change",
        )

        assert pair.baseline_simulation_id is not None
        assert pair.intervention_simulation_id is not None
        assert pair.baseline_simulation_id != pair.intervention_simulation_id

        # Verify the linked simulations actually exist
        baseline = await db_session.get(Simulation, pair.baseline_simulation_id)
        intervention = await db_session.get(Simulation, pair.intervention_simulation_id)
        assert baseline is not None
        assert intervention is not None

    @pytest.mark.asyncio
    async def test_scenario_pair_same_population(self, db_session):
        """両方のシミュレーションが同じ population_id を参照することを検証"""
        pop = Population(agent_count=300)
        db_session.add(pop)
        await db_session.commit()

        pair = await create_scenario_pair(
            session=db_session,
            population_id=pop.id,
            intervention_params={"incentive": "bonus"},
            decision_context="Incentive program",
            seed=7,
        )

        baseline = await db_session.get(Simulation, pair.baseline_simulation_id)
        intervention = await db_session.get(Simulation, pair.intervention_simulation_id)
        assert baseline.population_id == pop.id
        assert intervention.population_id == pop.id
        assert baseline.population_id == intervention.population_id

    @pytest.mark.asyncio
    async def test_scenario_pair_stores_intervention_params(self, db_session):
        """intervention_params JSON が永続化されることを検証"""
        pop = Population(agent_count=100)
        db_session.add(pop)
        await db_session.commit()

        params = {"policy_type": "subsidy", "amount": 5000, "target": "elderly", "duration": 24}
        pair = await create_scenario_pair(
            session=db_session,
            population_id=pop.id,
            intervention_params=params,
            decision_context="Elderly care subsidy",
        )

        fetched = await db_session.get(ScenarioPair, pair.id)
        assert fetched.intervention_params == params
        assert fetched.intervention_params["policy_type"] == "subsidy"
        assert fetched.intervention_params["amount"] == 5000
        assert fetched.intervention_params["target"] == "elderly"
        assert fetched.intervention_params["duration"] == 24

    @pytest.mark.asyncio
    async def test_scenario_pair_default_status(self, db_session):
        """status が "created" であることを検証"""
        pop = Population(agent_count=50)
        db_session.add(pop)
        await db_session.commit()

        pair = await create_scenario_pair(
            session=db_session,
            population_id=pop.id,
            intervention_params={},
            decision_context="Default status test",
        )

        fetched = await db_session.get(ScenarioPair, pair.id)
        assert fetched.status == "created"

    @pytest.mark.asyncio
    async def test_simulation_has_scenario_pair_id(self, db_session):
        """ファクトリで作成された Simulation に scenario_pair_id が設定されることを検証"""
        pop = Population(agent_count=150)
        db_session.add(pop)
        await db_session.commit()

        pair = await create_scenario_pair(
            session=db_session,
            population_id=pop.id,
            intervention_params={"change": "yes"},
            decision_context="Pair ID linkage test",
            seed=99,
        )

        baseline = await db_session.get(Simulation, pair.baseline_simulation_id)
        intervention = await db_session.get(Simulation, pair.intervention_simulation_id)

        assert baseline.scenario_pair_id == pair.id
        assert intervention.scenario_pair_id == pair.id
