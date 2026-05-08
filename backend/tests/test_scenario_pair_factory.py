"""Scenario Pair Factory のテスト (Stream C)"""

import pytest
from sqlalchemy import select

from src.app.models.agent_profile import AgentProfile
from src.app.models.population import Population
from src.app.models.population_snapshot import PopulationSnapshot
from src.app.models.scenario_pair import ScenarioPair
from src.app.models.simulation import Simulation
from src.app.services.scenario_pair_factory import create_scenario_pair


def _make_agent(population_id: str, index: int) -> AgentProfile:
    """テスト用 AgentProfile を作成するヘルパー"""
    return AgentProfile(
        population_id=population_id,
        agent_index=index,
        demographics={"age": 30 + index, "gender": "M", "occupation": "engineer"},
        big_five={"O": 0.7, "C": 0.6, "E": 0.5, "A": 0.8, "N": 0.3},
        values={"fairness": 0.9},
        life_event="test event",
        contradiction="test contradiction",
        information_source="news",
        local_context="urban",
        hidden_motivation="growth",
        speech_style="formal",
        shock_sensitivity={"economy": 0.5},
        llm_backend="openai",
        memory_summary="",
    )


class TestCreateScenarioPair:
    @pytest.mark.asyncio
    async def test_create_scenario_pair(self, db_session):
        """ScenarioPair + 2 Simulations が作成されることを検証"""
        pop = Population(agent_count=3, status="ready")
        db_session.add(pop)
        await db_session.flush()
        for i in range(3):
            db_session.add(_make_agent(pop.id, i))
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
        pop = Population(agent_count=3, status="ready")
        db_session.add(pop)
        await db_session.flush()
        for i in range(3):
            db_session.add(_make_agent(pop.id, i))
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
    async def test_scenario_pair_isolated_populations(self, db_session):
        """両子シミュレーションが独立した population_id を持つことを検証"""
        pop = Population(agent_count=3, status="ready")
        db_session.add(pop)
        await db_session.flush()
        for i in range(3):
            db_session.add(_make_agent(pop.id, i))
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
        # 両子は元の population_id とは異なるクローンを使用する
        assert baseline.population_id != pop.id
        assert intervention.population_id != pop.id
        # 両子同士も異なる population_id を持つ
        assert baseline.population_id != intervention.population_id

    @pytest.mark.asyncio
    async def test_scenario_pair_stores_intervention_params(self, db_session):
        """intervention_params JSON が永続化されることを検証"""
        pop = Population(agent_count=3, status="ready")
        db_session.add(pop)
        await db_session.flush()
        for i in range(3):
            db_session.add(_make_agent(pop.id, i))
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
        pop = Population(agent_count=3, status="ready")
        db_session.add(pop)
        await db_session.flush()
        for i in range(3):
            db_session.add(_make_agent(pop.id, i))
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
        pop = Population(agent_count=3, status="ready")
        db_session.add(pop)
        await db_session.flush()
        for i in range(3):
            db_session.add(_make_agent(pop.id, i))
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

    @pytest.mark.asyncio
    async def test_snapshot_contains_real_agents(self, db_session):
        """PopulationSnapshot に実際のエージェントデータ（id/information_sources 含む）が保存されることを検証"""
        pop = Population(agent_count=3, status="ready")
        db_session.add(pop)
        await db_session.flush()
        for i in range(3):
            db_session.add(_make_agent(pop.id, i))
        await db_session.commit()

        pair = await create_scenario_pair(
            session=db_session,
            population_id=pop.id,
            intervention_params={"policy": "test"},
            decision_context="Snapshot test",
            seed=42,
        )

        snapshot = await db_session.get(PopulationSnapshot, pair.population_snapshot_id)
        assert isinstance(snapshot.agent_profiles_json, list)
        assert len(snapshot.agent_profiles_json) == 3
        # スナップショット再生に必要な全フィールドが含まれることを確認
        agent = snapshot.agent_profiles_json[0]
        assert "id" in agent
        assert "population_id" in agent
        assert "information_sources" in agent

    @pytest.mark.asyncio
    async def test_cloned_populations_exist_and_ready(self, db_session):
        """クローン先の Population が存在し status='ready' でエージェントを持つことを検証"""
        pop = Population(agent_count=3, status="ready")
        db_session.add(pop)
        await db_session.flush()
        for i in range(3):
            db_session.add(_make_agent(pop.id, i))
        await db_session.commit()

        pair = await create_scenario_pair(
            session=db_session,
            population_id=pop.id,
            intervention_params={"policy": "test"},
            decision_context="Clone test",
            seed=42,
        )

        baseline = await db_session.get(Simulation, pair.baseline_simulation_id)
        intervention = await db_session.get(Simulation, pair.intervention_simulation_id)

        for sim in (baseline, intervention):
            cloned_pop = await db_session.get(Population, sim.population_id)
            assert cloned_pop is not None
            assert cloned_pop.status == "ready"
            assert cloned_pop.parent_id == pop.id
            result = await db_session.execute(
                select(AgentProfile).where(AgentProfile.population_id == sim.population_id)
            )
            agents = result.scalars().all()
            assert len(agents) == 3

    @pytest.mark.asyncio
    async def test_create_scenario_pair_raises_on_no_agents(self, db_session):
        """エージェントが存在しない Population ではエラーになることを検証"""
        pop = Population(agent_count=0, status="ready")
        db_session.add(pop)
        await db_session.commit()

        with pytest.raises(ValueError, match="no agent"):
            await create_scenario_pair(
                session=db_session,
                population_id=pop.id,
                intervention_params={},
                decision_context="Empty pop test",
            )
