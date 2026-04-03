"""Decision Laboratory モデルのテスト (Stream A)"""

import pytest
from sqlalchemy import select


class TestPopulationSnapshot:
    @pytest.mark.asyncio
    async def test_create_population_snapshot(self, db_session):
        from src.app.models.population import Population
        from src.app.models.population_snapshot import PopulationSnapshot

        pop = Population(agent_count=500)
        db_session.add(pop)
        await db_session.commit()

        snapshot = PopulationSnapshot(
            population_id=pop.id,
            agent_profiles_json=[{"name": "Agent A", "age": 30}],
            relationships_json={"edges": [["a1", "a2"]]},
            initial_beliefs_json={"a1": {"stance": 0.5}},
            seed=42,
        )
        db_session.add(snapshot)
        await db_session.commit()

        fetched = await db_session.get(PopulationSnapshot, snapshot.id)
        assert fetched is not None
        assert fetched.population_id == pop.id
        assert fetched.seed == 42
        assert fetched.agent_profiles_json == [{"name": "Agent A", "age": 30}]
        assert fetched.relationships_json == {"edges": [["a1", "a2"]]}
        assert fetched.initial_beliefs_json == {"a1": {"stance": 0.5}}
        assert fetched.created_at is not None

    @pytest.mark.asyncio
    async def test_query_snapshots_by_population(self, db_session):
        from src.app.models.population import Population
        from src.app.models.population_snapshot import PopulationSnapshot

        pop = Population(agent_count=100)
        db_session.add(pop)
        await db_session.commit()

        for seed in range(3):
            db_session.add(PopulationSnapshot(
                population_id=pop.id,
                agent_profiles_json=[],
                relationships_json={},
                initial_beliefs_json={},
                seed=seed,
            ))
        await db_session.commit()

        stmt = select(PopulationSnapshot).where(PopulationSnapshot.population_id == pop.id)
        result = await db_session.execute(stmt)
        snapshots = result.scalars().all()
        assert len(snapshots) == 3


class TestScenarioPair:
    @pytest.mark.asyncio
    async def test_create_scenario_pair(self, db_session):
        from src.app.models.population import Population
        from src.app.models.population_snapshot import PopulationSnapshot
        from src.app.models.simulation import Simulation
        from src.app.models.scenario_pair import ScenarioPair

        pop = Population(agent_count=200)
        db_session.add(pop)
        await db_session.commit()

        snapshot = PopulationSnapshot(
            population_id=pop.id,
            agent_profiles_json=[],
            relationships_json={},
            initial_beliefs_json={},
            seed=99,
        )
        db_session.add(snapshot)
        await db_session.commit()

        sim_base = Simulation(mode="standard", prompt_text="baseline", template_name="general", execution_profile="standard")
        sim_intv = Simulation(mode="standard", prompt_text="intervention", template_name="general", execution_profile="standard")
        db_session.add_all([sim_base, sim_intv])
        await db_session.commit()

        pair = ScenarioPair(
            population_snapshot_id=snapshot.id,
            baseline_simulation_id=sim_base.id,
            intervention_simulation_id=sim_intv.id,
            intervention_params={"policy_type": "subsidy", "amount": 1000, "target_population": "youth", "duration": 12},
            decision_context="Youth employment subsidy policy",
            status="created",
        )
        db_session.add(pair)
        await db_session.commit()

        fetched = await db_session.get(ScenarioPair, pair.id)
        assert fetched is not None
        assert fetched.population_snapshot_id == snapshot.id
        assert fetched.baseline_simulation_id == sim_base.id
        assert fetched.intervention_simulation_id == sim_intv.id
        assert fetched.intervention_params["policy_type"] == "subsidy"
        assert fetched.decision_context == "Youth employment subsidy policy"
        assert fetched.status == "created"
        assert fetched.created_at is not None

    @pytest.mark.asyncio
    async def test_create_scenario_pair_nullable_simulations(self, db_session):
        from src.app.models.population import Population
        from src.app.models.population_snapshot import PopulationSnapshot
        from src.app.models.scenario_pair import ScenarioPair

        pop = Population(agent_count=50)
        db_session.add(pop)
        await db_session.commit()

        snapshot = PopulationSnapshot(
            population_id=pop.id,
            agent_profiles_json=[],
            relationships_json={},
            initial_beliefs_json={},
            seed=1,
        )
        db_session.add(snapshot)
        await db_session.commit()

        pair = ScenarioPair(
            population_snapshot_id=snapshot.id,
            intervention_params={},
            decision_context="Draft scenario",
        )
        db_session.add(pair)
        await db_session.commit()

        fetched = await db_session.get(ScenarioPair, pair.id)
        assert fetched.baseline_simulation_id is None
        assert fetched.intervention_simulation_id is None


class TestAuditEvent:
    @pytest.mark.asyncio
    async def test_create_audit_event(self, db_session):
        from src.app.models.simulation import Simulation
        from src.app.models.audit_event import AuditEvent

        sim = Simulation(mode="standard", prompt_text="test", template_name="general", execution_profile="standard")
        db_session.add(sim)
        await db_session.commit()

        event = AuditEvent(
            simulation_id=sim.id,
            agent_id="agent-001",
            agent_name="Alice",
            round_number=3,
            event_type="belief_change",
            before_state={"stance": 0.3, "confidence": 0.8},
            after_state={"stance": 0.6, "confidence": 0.9},
            reasoning="Influenced by peer discussion on economic data",
        )
        db_session.add(event)
        await db_session.commit()

        fetched = await db_session.get(AuditEvent, event.id)
        assert fetched is not None
        assert fetched.simulation_id == sim.id
        assert fetched.agent_id == "agent-001"
        assert fetched.agent_name == "Alice"
        assert fetched.round_number == 3
        assert fetched.event_type == "belief_change"
        assert fetched.before_state["stance"] == 0.3
        assert fetched.after_state["stance"] == 0.6
        assert fetched.reasoning == "Influenced by peer discussion on economic data"
        assert fetched.created_at is not None

    @pytest.mark.asyncio
    async def test_query_audit_events_by_simulation(self, db_session):
        from src.app.models.simulation import Simulation
        from src.app.models.audit_event import AuditEvent

        sim = Simulation(mode="standard", prompt_text="test", template_name="general", execution_profile="standard")
        db_session.add(sim)
        await db_session.commit()

        for i in range(5):
            db_session.add(AuditEvent(
                simulation_id=sim.id,
                agent_id=f"agent-{i}",
                agent_name=f"Agent {i}",
                round_number=1,
                event_type="opinion_shift",
                before_state={"v": i},
                after_state={"v": i + 1},
                reasoning=f"Shift {i}",
            ))
        await db_session.commit()

        stmt = select(AuditEvent).where(AuditEvent.simulation_id == sim.id)
        result = await db_session.execute(stmt)
        events = result.scalars().all()
        assert len(events) == 5


class TestSimulationScenarioPairId:
    @pytest.mark.asyncio
    async def test_scenario_pair_id_default_none(self, db_session):
        from src.app.models.simulation import Simulation

        sim = Simulation(
            mode="standard",
            prompt_text="test",
            template_name="general",
            execution_profile="standard",
        )
        db_session.add(sim)
        await db_session.commit()

        fetched = await db_session.get(Simulation, sim.id)
        assert fetched.scenario_pair_id is None

    @pytest.mark.asyncio
    async def test_scenario_pair_id_set(self, db_session):
        from src.app.models.simulation import Simulation

        sim = Simulation(
            mode="standard",
            prompt_text="test",
            template_name="general",
            execution_profile="standard",
            scenario_pair_id="pair-abc-123",
        )
        db_session.add(sim)
        await db_session.commit()

        fetched = await db_session.get(Simulation, sim.id)
        assert fetched.scenario_pair_id == "pair-abc-123"
