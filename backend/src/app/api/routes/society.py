"""Society モード API エンドポイント"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.models.population import Population
from src.app.models.agent_profile import AgentProfile
from src.app.models.society_result import SocietyResult
from src.app.models.evaluation_result import EvaluationResult
from src.app.services.society.population_generator import generate_population

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/populations")
async def list_populations(session: AsyncSession = Depends(get_session)):
    """利用可能な人口リスト。"""
    result = await session.execute(
        select(Population).order_by(Population.created_at.desc()).limit(20)
    )
    pops = result.scalars().all()
    return [
        {
            "id": p.id,
            "version": p.version,
            "agent_count": p.agent_count,
            "status": p.status,
            "created_at": p.created_at.isoformat(),
        }
        for p in pops
    ]


class PopulationGenerateRequest(BaseModel):
    count: int = 1000
    seed: int | None = None


@router.post("/populations/generate")
async def generate_population_endpoint(
    body: PopulationGenerateRequest,
    session: AsyncSession = Depends(get_session),
):
    """人口生成をトリガーする。"""
    if body.count < 100 or body.count > 10000:
        raise HTTPException(status_code=400, detail="count は 100〜10000 の範囲で指定してください")

    pop_id = str(uuid.uuid4())
    population = Population(
        id=pop_id,
        agent_count=body.count,
        generation_params={"count": body.count, "seed": body.seed},
        status="generating",
    )
    session.add(population)
    await session.commit()

    # 同期的に生成（小さいので高速）
    agents = await generate_population(pop_id, body.count, seed=body.seed)
    for agent_data in agents:
        profile = AgentProfile(**agent_data)
        session.add(profile)

    population.status = "ready"
    await session.commit()

    return {
        "id": pop_id,
        "agent_count": len(agents),
        "status": "ready",
    }


@router.get("/simulations/{sim_id}/activation")
async def get_activation_result(
    sim_id: str,
    session: AsyncSession = Depends(get_session),
):
    """活性化レイヤーの結果を取得する。"""
    result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "activation")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="活性化結果が見つかりません")

    return {
        "id": record.id,
        "simulation_id": record.simulation_id,
        "population_id": record.population_id,
        "phase_data": record.phase_data,
        "usage": record.usage,
        "created_at": record.created_at.isoformat(),
    }


@router.post("/populations/{pop_id}/fork")
async def fork_population(
    pop_id: str,
    session: AsyncSession = Depends(get_session),
):
    """既存の人口から新世代を作成する（記憶を引き継ぐ）。"""
    parent = await session.get(Population, pop_id)
    if not parent or parent.status != "ready":
        raise HTTPException(status_code=404, detail="親の人口が見つからないか準備中です")

    # 親のエージェントを取得
    result = await session.execute(
        select(AgentProfile).where(AgentProfile.population_id == pop_id)
    )
    parent_agents = result.scalars().all()
    if not parent_agents:
        raise HTTPException(status_code=404, detail="親の人口にエージェントがいません")

    # 新世代を作成
    new_pop_id = str(uuid.uuid4())
    new_pop = Population(
        id=new_pop_id,
        parent_id=pop_id,
        version=parent.version + 1,
        agent_count=parent.agent_count,
        generation_params={**parent.generation_params, "forked_from": pop_id},
        status="generating",
    )
    session.add(new_pop)
    await session.commit()

    # エージェントをコピー（memory_summary を引き継ぐ）
    for agent in parent_agents:
        new_agent = AgentProfile(
            id=str(uuid.uuid4()),
            population_id=new_pop_id,
            agent_index=agent.agent_index,
            demographics=agent.demographics,
            big_five=agent.big_five,
            values=agent.values,
            life_event=agent.life_event,
            contradiction=agent.contradiction,
            information_source=agent.information_source,
            local_context=agent.local_context,
            hidden_motivation=agent.hidden_motivation,
            speech_style=agent.speech_style,
            shock_sensitivity=agent.shock_sensitivity,
            llm_backend=agent.llm_backend,
            memory_summary=agent.memory_summary,  # 記憶を引き継ぐ
        )
        session.add(new_agent)

    new_pop.status = "ready"
    await session.commit()

    return {
        "id": new_pop_id,
        "parent_id": pop_id,
        "version": new_pop.version,
        "agent_count": new_pop.agent_count,
        "status": "ready",
    }


@router.get("/populations/{pop_id}")
async def get_population_detail(
    pop_id: str,
    session: AsyncSession = Depends(get_session),
):
    """人口の詳細情報を取得する。"""
    pop = await session.get(Population, pop_id)
    if not pop:
        raise HTTPException(status_code=404, detail="人口が見つかりません")

    # エージェントのサンプル（最初の20人）
    result = await session.execute(
        select(AgentProfile)
        .where(AgentProfile.population_id == pop_id)
        .order_by(AgentProfile.agent_index)
        .limit(20)
    )
    sample_agents = result.scalars().all()

    return {
        "id": pop.id,
        "parent_id": pop.parent_id,
        "version": pop.version,
        "agent_count": pop.agent_count,
        "status": pop.status,
        "generation_params": pop.generation_params,
        "created_at": pop.created_at.isoformat(),
        "sample_agents": [
            {
                "id": a.id,
                "agent_index": a.agent_index,
                "demographics": a.demographics,
                "big_five": a.big_five,
                "llm_backend": a.llm_backend,
                "memory_summary": a.memory_summary[:200] if a.memory_summary else "",
            }
            for a in sample_agents
        ],
    }


@router.get("/simulations/{sim_id}/meeting")
async def get_meeting_result(
    sim_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Meeting Layer の結果を取得する。"""
    result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "meeting")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Meeting結果が見つかりません")

    return {
        "id": record.id,
        "simulation_id": record.simulation_id,
        "phase_data": record.phase_data,
        "usage": record.usage,
        "created_at": record.created_at.isoformat(),
    }


@router.get("/simulations/{sim_id}/evaluation")
async def get_evaluation_result(
    sim_id: str,
    session: AsyncSession = Depends(get_session),
):
    """評価メトリクスを取得する。"""
    result = await session.execute(
        select(EvaluationResult).where(EvaluationResult.simulation_id == sim_id)
    )
    metrics = result.scalars().all()
    if not metrics:
        raise HTTPException(status_code=404, detail="評価結果が見つかりません")

    return [
        {
            "id": m.id,
            "metric_name": m.metric_name,
            "score": m.score,
            "details": m.details,
            "baseline_type": m.baseline_type,
            "baseline_score": m.baseline_score,
            "created_at": m.created_at.isoformat(),
        }
        for m in metrics
    ]
