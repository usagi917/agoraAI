"""Scenario Pair Factory: ベースライン vs 介入シミュレーションペアの作成"""

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.population_snapshot import PopulationSnapshot
from src.app.models.scenario_pair import ScenarioPair
from src.app.models.simulation import Simulation

logger = logging.getLogger(__name__)


async def create_scenario_pair(
    session: AsyncSession,
    population_id: str,
    intervention_params: dict,
    decision_context: str,
    preset: str = "standard",
    seed: int | None = None,
) -> ScenarioPair:
    """Create a ScenarioPair with baseline + intervention Simulation records.

    1. Create a PopulationSnapshot placeholder (store population_id, seed)
    2. Create baseline Simulation (mode=preset, population_id, seed, scenario_pair_id)
    3. Create intervention Simulation (same params + scenario_pair_id)
    4. Create ScenarioPair record linking everything
    5. Return the ScenarioPair
    """
    # 1. PopulationSnapshot placeholder
    snapshot = PopulationSnapshot(
        population_id=population_id,
        agent_profiles_json=[],
        relationships_json={},
        initial_beliefs_json={},
        seed=seed if seed is not None else 0,
    )
    session.add(snapshot)
    await session.flush()

    # 2-4. Create ScenarioPair first (need id for simulations)
    pair = ScenarioPair(
        population_snapshot_id=snapshot.id,
        intervention_params=intervention_params,
        decision_context=decision_context,
        status="created",
    )
    session.add(pair)
    await session.flush()

    # 2. Baseline Simulation
    sim_baseline = Simulation(
        mode=preset,
        prompt_text=decision_context,
        template_name="general",
        execution_profile="standard",
        population_id=population_id,
        seed=seed,
        scenario_pair_id=pair.id,
    )
    session.add(sim_baseline)

    # 3. Intervention Simulation — inject intervention_params into prompt
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
        population_id=population_id,
        seed=seed,
        scenario_pair_id=pair.id,
    )
    session.add(sim_intervention)
    await session.flush()

    # 4. Link simulations to the pair
    pair.baseline_simulation_id = sim_baseline.id
    pair.intervention_simulation_id = sim_intervention.id
    await session.commit()
    await session.refresh(pair)

    logger.info(
        "Created scenario pair %s (baseline=%s, intervention=%s) for population %s",
        pair.id,
        sim_baseline.id,
        sim_intervention.id,
        population_id,
    )
    return pair
