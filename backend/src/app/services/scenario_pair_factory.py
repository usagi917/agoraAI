"""Scenario Pair Factory: ベースライン vs 介入シミュレーションペアの作成"""

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.agent_profile import AgentProfile
from src.app.models.population import Population
from src.app.models.population_snapshot import PopulationSnapshot
from src.app.models.scenario_pair import ScenarioPair
from src.app.models.simulation import Simulation
from src.app.models.social_edge import SocialEdge

logger = logging.getLogger(__name__)


def _serialize_agent(a: AgentProfile) -> dict:
    """AgentProfile ORM → dict 変換（スナップショット再生に必要な全フィールドを保持）"""
    return {
        "id": a.id,
        "population_id": a.population_id,
        "agent_index": a.agent_index,
        "demographics": a.demographics,
        "big_five": a.big_five,
        "values": a.values,
        "life_event": a.life_event,
        "contradiction": a.contradiction,
        "information_source": a.information_source,
        "information_sources": a.information_sources,
        "local_context": a.local_context,
        "hidden_motivation": a.hidden_motivation,
        "speech_style": a.speech_style,
        "shock_sensitivity": a.shock_sensitivity,
        "llm_backend": a.llm_backend,
        "memory_summary": a.memory_summary,
    }


async def _clone_population(
    session: AsyncSession,
    source_population_id: str,
    agents_data: list[dict],
) -> str:
    """Population をクローンし、AgentProfile と SocialEdge を複製して新しい population_id を返す。"""
    clone_id = str(uuid.uuid4())
    clone = Population(
        id=clone_id,
        parent_id=source_population_id,
        agent_count=len(agents_data),
        generation_params={"cloned_from": source_population_id},
        status="ready",
    )
    session.add(clone)

    # old agent UUID → new agent UUID のマッピングを構築
    id_map: dict[str, str] = {}
    for agent_data in agents_data:
        new_id = str(uuid.uuid4())
        id_map[agent_data["id"]] = new_id
        clone_fields = {k: v for k, v in agent_data.items() if k not in ("id", "population_id")}
        profile = AgentProfile(
            id=new_id,
            population_id=clone_id,
            **clone_fields,
        )
        session.add(profile)

    # SocialEdge を複製（agent_id / target_id を新 UUID にリマップ）
    edges_result = await session.execute(
        select(SocialEdge).where(SocialEdge.population_id == source_population_id)
    )
    for edge in edges_result.scalars().all():
        new_agent_id = id_map.get(edge.agent_id)
        new_target_id = id_map.get(edge.target_id)
        if new_agent_id and new_target_id:
            session.add(SocialEdge(
                population_id=clone_id,
                agent_id=new_agent_id,
                target_id=new_target_id,
                relation_type=edge.relation_type,
                strength=edge.strength,
            ))

    await session.flush()
    return clone_id


async def create_scenario_pair(
    session: AsyncSession,
    population_id: str,
    intervention_params: dict,
    decision_context: str,
    preset: str = "standard",
    seed: int | None = None,
) -> ScenarioPair:
    """Create a ScenarioPair with baseline + intervention Simulation records.

    1. Load real agents from source population and create a genuine snapshot
    2. Clone the population for baseline and intervention (isolation)
    3. Create baseline Simulation with cloned population
    4. Create intervention Simulation with cloned population
    5. Create ScenarioPair record linking everything
    6. Return the ScenarioPair
    """
    # 1. Load real agents from source population
    result = await session.execute(
        select(AgentProfile).where(AgentProfile.population_id == population_id)
    )
    agents_db = result.scalars().all()
    if not agents_db:
        raise ValueError(
            f"Population {population_id} has no agent profiles — "
            "cannot create scenario pair"
        )
    agents_data = [_serialize_agent(a) for a in agents_db]

    # Create genuine snapshot with real agent data
    resolved_seed = seed if seed is not None else 0
    snapshot = PopulationSnapshot(
        population_id=population_id,
        agent_profiles_json=agents_data,
        relationships_json={},
        initial_beliefs_json={},
        seed=resolved_seed,
    )
    session.add(snapshot)
    await session.flush()

    # 2. Clone populations for isolation
    baseline_pop_id = await _clone_population(session, population_id, agents_data)
    intervention_pop_id = await _clone_population(session, population_id, agents_data)

    # 3-5. Create ScenarioPair first (need id for simulations)
    pair = ScenarioPair(
        population_snapshot_id=snapshot.id,
        intervention_params=intervention_params,
        decision_context=decision_context,
        status="created",
    )
    session.add(pair)
    await session.flush()

    # 3. Baseline Simulation — uses cloned population
    sim_baseline = Simulation(
        mode=preset,
        prompt_text=decision_context,
        template_name="general",
        execution_profile="standard",
        population_id=baseline_pop_id,
        seed=seed,
        scenario_pair_id=pair.id,
    )
    session.add(sim_baseline)

    # 4. Intervention Simulation — uses separate cloned population
    intervention_prompt = (
        f"{decision_context}\n\n"
        f"【介入パラメータ】\n"
        f"{json.dumps(intervention_params, ensure_ascii=False, indent=2)}"
    )
    sim_intervention = Simulation(
        mode=preset,
        prompt_text=intervention_prompt,
        template_name="general",
        execution_profile="standard",
        population_id=intervention_pop_id,
        seed=seed,
        scenario_pair_id=pair.id,
    )
    session.add(sim_intervention)
    await session.flush()

    # 5. Link simulations to the pair
    pair.baseline_simulation_id = sim_baseline.id
    pair.intervention_simulation_id = sim_intervention.id
    await session.commit()
    await session.refresh(pair)

    logger.info(
        "Created scenario pair %s (baseline=%s pop=%s, intervention=%s pop=%s) "
        "from source population %s",
        pair.id,
        sim_baseline.id,
        baseline_pop_id,
        sim_intervention.id,
        intervention_pop_id,
        population_id,
    )
    return pair
