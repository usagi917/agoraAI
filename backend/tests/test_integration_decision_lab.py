"""Stream H1: E2E Backend Integration Tests for Decision Laboratory

Tests the full backend flow WITHOUT real LLM calls (all mocks).
Validates: scenario pair creation, audit trail recording, snapshot
round-tripping, and scenario comparison assembly.
"""

import pytest

from src.app.models.population import Population
from src.app.models.simulation import Simulation
from src.app.models.scenario_pair import ScenarioPair
from src.app.services.audit_trail_service import (
    get_audit_trail,
    get_opinion_shifts,
    record_event,
)
from src.app.services.population_snapshot_service import (
    create_snapshot,
    restore_from_snapshot,
)
from src.app.services.scenario_comparison import (
    build_coalition_map,
    build_delta_brief,
)
from src.app.services.scenario_pair_factory import create_scenario_pair


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rich_agents(count: int = 5) -> list[dict]:
    """Generate agent dicts with demographics, big_five, values, etc."""
    age_brackets = ["18-29", "30-49", "50+", "18-29", "30-49"]
    regions = ["Tokyo", "Osaka", "Tokyo", "Osaka", "Tokyo"]
    occupations = ["student", "engineer", "self_employed", "student", "engineer"]
    values = ["education", "economy", "safety", "education", "economy"]
    stances = [0.8, 0.3, 0.2, 0.6, 0.9]

    return [
        {
            "id": f"agent-{i}",
            "population_id": "pop-test",
            "agent_index": i,
            "demographics": {
                "age": 25 + i * 5,
                "gender": "male" if i % 2 == 0 else "female",
                "occupation": occupations[i],
                "region": regions[i],
                "income_bracket": "middle",
                "education": "bachelor",
            },
            "big_five": {
                "O": 0.6 + i * 0.02,
                "C": 0.5,
                "E": 0.5,
                "A": 0.5,
                "N": 0.5,
            },
            "values": {values[i]: 0.6, "freedom": 0.4},
            "age_bracket": age_brackets[i],
            "region": regions[i],
            "occupation": occupations[i],
            "primary_value": values[i],
            "stance": stances[i],
            "life_event": "test event",
            "speech_style": "analytical",
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# H1.1: Full scenario pair flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_scenario_pair_flow(db_session):
    """End-to-end: create pair -> record audits -> build comparison."""
    # Setup: create a population record
    pop = Population(agent_count=5)
    db_session.add(pop)
    await db_session.commit()

    # Step 1: create_scenario_pair
    pair = await create_scenario_pair(
        session=db_session,
        population_id=pop.id,
        intervention_params={"policy_type": "subsidy", "amount": 5000},
        decision_context="Youth employment subsidy policy evaluation",
        preset="standard",
        seed=42,
    )

    # Step 2: verify pair.status == "created", both sim IDs set
    assert pair.status == "created"
    assert pair.baseline_simulation_id is not None
    assert pair.intervention_simulation_id is not None
    assert pair.population_snapshot_id is not None
    assert pair.intervention_params["policy_type"] == "subsidy"
    assert pair.decision_context == "Youth employment subsidy policy evaluation"

    # Verify the two simulation records exist and link back
    baseline_sim = await db_session.get(Simulation, pair.baseline_simulation_id)
    intervention_sim = await db_session.get(Simulation, pair.intervention_simulation_id)
    assert baseline_sim is not None
    assert intervention_sim is not None
    assert baseline_sim.scenario_pair_id == pair.id
    assert intervention_sim.scenario_pair_id == pair.id
    assert baseline_sim.population_id == pop.id
    assert intervention_sim.population_id == pop.id
    assert baseline_sim.seed == 42
    assert intervention_sim.seed == 42

    # Step 3: record audit events for baseline simulation
    for round_num in range(1, 4):
        await record_event(
            session=db_session,
            simulation_id=str(baseline_sim.id),
            agent_id=f"agent-{round_num}",
            agent_name=f"Agent B{round_num}",
            round_number=round_num,
            event_type="opinion_shift" if round_num % 2 == 1 else "belief_change",
            before_state={"stance": 0.3 + round_num * 0.05},
            after_state={"stance": 0.5 + round_num * 0.05},
            reasoning=f"Baseline shift round {round_num}",
        )
    await db_session.commit()

    # Step 4: record audit events for intervention simulation
    for round_num in range(1, 4):
        await record_event(
            session=db_session,
            simulation_id=str(intervention_sim.id),
            agent_id=f"agent-{round_num}",
            agent_name=f"Agent I{round_num}",
            round_number=round_num,
            event_type="opinion_shift",
            before_state={"stance": 0.4 + round_num * 0.05},
            after_state={"stance": 0.7 + round_num * 0.05},
            reasoning=f"Intervention shift round {round_num}",
        )
    await db_session.commit()

    # Step 5: call build_delta_brief with mock briefs
    baseline_brief = {
        "recommendation": "No-Go",
        "agreement_score": 0.40,
        "key_reasons": [{"reason": "High cost", "confidence": 0.6}],
        "guardrails": [{"condition": "Budget available", "status": "unknown"}],
        "critical_unknowns": [{"question": "Long-term fiscal impact"}],
    }
    intervention_brief = {
        "recommendation": "Go",
        "agreement_score": 0.72,
        "key_reasons": [
            {"reason": "High cost", "confidence": 0.7},
            {"reason": "Youth retention improved", "confidence": 0.8},
        ],
        "guardrails": [{"condition": "Budget available", "status": "confirmed"}],
        "critical_unknowns": [{"question": "Political opposition"}],
    }
    delta = build_delta_brief(baseline_brief, intervention_brief)

    # Step 6: verify delta has expected sections
    assert "support_change" in delta
    assert delta["support_change"] == round(0.72 - 0.40, 4)
    assert delta["support_change"] > 0

    assert "new_concerns" in delta
    assert "Political opposition" in delta["new_concerns"]

    assert "resolved_concerns" in delta
    assert "Long-term fiscal impact" in delta["resolved_concerns"]

    assert "key_differences" in delta
    assert len(delta["key_differences"]) >= 1
    assert len(delta["key_differences"]) <= 3

    assert delta["recommendation_change"] is not None
    assert delta["recommendation_change"]["before"] == "No-Go"
    assert delta["recommendation_change"]["after"] == "Go"

    # Step 7: call build_coalition_map with mock agents
    agents = _make_rich_agents(5)
    coalition_map = build_coalition_map(agents)

    # Step 8: verify coalition_map structure
    assert "by_age" in coalition_map
    assert "by_region" in coalition_map
    assert "by_occupation" in coalition_map
    assert "by_value" in coalition_map

    # Each group should have group, support, oppose, count
    for dimension in ("by_age", "by_region", "by_occupation", "by_value"):
        for group_entry in coalition_map[dimension]:
            assert "group" in group_entry
            assert "support" in group_entry
            assert "oppose" in group_entry
            assert "count" in group_entry
            assert abs(group_entry["support"] + group_entry["oppose"] - 1.0) < 0.001


# ---------------------------------------------------------------------------
# H1.2: Snapshot restore consistency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_restore_consistency(db_session):
    """Verify snapshot -> restore produces identical agent data."""
    pop = Population(agent_count=5)
    db_session.add(pop)
    await db_session.commit()

    original_agents = _make_rich_agents(5)

    # Create snapshot
    snapshot = await create_snapshot(
        session=db_session,
        population_id=pop.id,
        agents=original_agents,
        seed=99,
    )
    assert snapshot.id is not None
    assert snapshot.seed == 99

    # Restore from snapshot
    restored_agents = await restore_from_snapshot(db_session, snapshot.id)

    # Assert deep equality
    assert len(restored_agents) == len(original_agents)
    for original, restored in zip(original_agents, restored_agents):
        assert restored == original

    # Verify specific nested fields survived the JSON round-trip
    for i in range(len(original_agents)):
        assert restored_agents[i]["demographics"] == original_agents[i]["demographics"]
        assert restored_agents[i]["big_five"] == original_agents[i]["big_five"]
        assert restored_agents[i]["values"] == original_agents[i]["values"]
        assert restored_agents[i]["age_bracket"] == original_agents[i]["age_bracket"]
        assert restored_agents[i]["stance"] == original_agents[i]["stance"]


# ---------------------------------------------------------------------------
# H1.3: Audit trail across rounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_trail_across_rounds(db_session):
    """Record events across multiple rounds, verify ordering and filtering."""
    sim = Simulation(
        mode="standard",
        prompt_text="multi-round audit test",
        template_name="general",
        execution_profile="standard",
    )
    db_session.add(sim)
    await db_session.commit()

    # Record events for rounds 1-5, mix of agents and event types
    event_specs = [
        ("agent-A", "Agent A", 1, "belief_change"),
        ("agent-B", "Agent B", 1, "opinion_shift"),
        ("agent-A", "Agent A", 2, "action"),
        ("agent-C", "Agent C", 2, "opinion_shift"),
        ("agent-A", "Agent A", 3, "opinion_shift"),
        ("agent-B", "Agent B", 3, "belief_change"),
        ("agent-C", "Agent C", 4, "action"),
        ("agent-A", "Agent A", 4, "opinion_shift"),
        ("agent-B", "Agent B", 5, "opinion_shift"),
        ("agent-C", "Agent C", 5, "belief_change"),
    ]

    for agent_id, agent_name, round_num, event_type in event_specs:
        await record_event(
            session=db_session,
            simulation_id=sim.id,
            agent_id=agent_id,
            agent_name=agent_name,
            round_number=round_num,
            event_type=event_type,
            before_state={"stance": round_num * 0.1},
            after_state={"stance": round_num * 0.1 + 0.05},
            reasoning=f"{agent_name} round {round_num}",
        )
    await db_session.commit()

    # Query all -> verify total count
    all_events = await get_audit_trail(db_session, sim.id)
    assert len(all_events) == 10

    # Verify chronological order (created_at should be non-decreasing)
    for i in range(1, len(all_events)):
        assert all_events[i].created_at >= all_events[i - 1].created_at

    # Query by agent -> verify filter
    agent_a_events = await get_audit_trail(db_session, sim.id, agent_id="agent-A")
    assert len(agent_a_events) == 4
    assert all(e.agent_id == "agent-A" for e in agent_a_events)

    agent_b_events = await get_audit_trail(db_session, sim.id, agent_id="agent-B")
    assert len(agent_b_events) == 3
    assert all(e.agent_id == "agent-B" for e in agent_b_events)

    # Query opinion_shifts only -> verify filter
    # opinion_shift events: agent-B r1, agent-C r2, agent-A r3, agent-A r4, agent-B r5 = 5
    opinion_shifts = await get_audit_trail(
        db_session, sim.id, event_type="opinion_shift",
    )
    assert len(opinion_shifts) == 5
    assert all(e.event_type == "opinion_shift" for e in opinion_shifts)

    # Verify get_opinion_shifts returns only opinion_shift type
    shifts = await get_opinion_shifts(db_session, sim.id)
    assert len(shifts) == 5
    assert all(e.event_type == "opinion_shift" for e in shifts)

    # Query actions only
    actions = await get_audit_trail(db_session, sim.id, event_type="action")
    assert len(actions) == 2
    assert all(e.event_type == "action" for e in actions)


# ---------------------------------------------------------------------------
# H1.4: Scenario pair with intervention params
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_pair_with_intervention_params(db_session):
    """Verify intervention_params flow through the full chain."""
    pop = Population(agent_count=100)
    db_session.add(pop)
    await db_session.commit()

    intervention_params = {
        "policy_type": "tax_reform",
        "tax_rate": 0.25,
        "affected_sectors": ["manufacturing", "technology"],
        "phase_in_months": 12,
    }

    pair = await create_scenario_pair(
        session=db_session,
        population_id=pop.id,
        intervention_params=intervention_params,
        decision_context="Corporate tax reform impact analysis",
        preset="standard",
        seed=7,
    )

    # Verify params stored on ScenarioPair
    assert pair.intervention_params == intervention_params
    assert pair.intervention_params["tax_rate"] == 0.25
    assert pair.intervention_params["affected_sectors"] == ["manufacturing", "technology"]

    # Reload from DB to confirm persistence
    reloaded = await db_session.get(ScenarioPair, pair.id)
    assert reloaded is not None
    assert reloaded.intervention_params == intervention_params

    # Verify both simulations reference same population
    baseline = await db_session.get(Simulation, pair.baseline_simulation_id)
    intervention = await db_session.get(Simulation, pair.intervention_simulation_id)
    assert baseline.population_id == pop.id
    assert intervention.population_id == pop.id
    assert baseline.population_id == intervention.population_id

    # Verify both simulations share the same scenario_pair_id
    assert baseline.scenario_pair_id == pair.id
    assert intervention.scenario_pair_id == pair.id

    # Verify both simulations share the same seed
    assert baseline.seed == 7
    assert intervention.seed == 7

    # Verify simulation prompts match the decision context
    assert baseline.prompt_text == "Corporate tax reform impact analysis"
    assert intervention.prompt_text == "Corporate tax reform impact analysis"


# ---------------------------------------------------------------------------
# H1.5: Multiple scenario pairs for the same population
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_pairs_same_population(db_session):
    """Multiple scenario pairs can be created for the same population."""
    pop = Population(agent_count=50)
    db_session.add(pop)
    await db_session.commit()

    pair_a = await create_scenario_pair(
        session=db_session,
        population_id=pop.id,
        intervention_params={"variant": "A"},
        decision_context="Variant A test",
        seed=1,
    )
    pair_b = await create_scenario_pair(
        session=db_session,
        population_id=pop.id,
        intervention_params={"variant": "B"},
        decision_context="Variant B test",
        seed=2,
    )

    assert pair_a.id != pair_b.id
    assert pair_a.baseline_simulation_id != pair_b.baseline_simulation_id
    assert pair_a.intervention_simulation_id != pair_b.intervention_simulation_id

    # Each pair creates its own snapshot
    assert pair_a.population_snapshot_id != pair_b.population_snapshot_id


# ---------------------------------------------------------------------------
# H1.6: Delta brief with identical briefs produces zero changes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delta_brief_identical_produces_zero():
    """Identical briefs should produce no changes at all."""
    brief = {
        "recommendation": "Go",
        "agreement_score": 0.75,
        "key_reasons": [{"reason": "Strong demand", "confidence": 0.8}],
        "guardrails": [{"condition": "Funding secured", "status": "confirmed"}],
        "critical_unknowns": [],
    }
    delta = build_delta_brief(brief, brief)

    assert delta["support_change"] == 0.0
    assert delta["recommendation_change"] is None
    assert delta["new_concerns"] == []
    assert delta["resolved_concerns"] == []
    assert delta["guardrail_changes"] == []
    assert delta["key_differences"] == []
    assert delta["coalition_shifts"] == []
