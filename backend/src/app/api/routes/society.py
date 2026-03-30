"""Society モード API エンドポイント"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.models.population import Population
from src.app.models.agent_profile import AgentProfile
from src.app.models.social_edge import SocialEdge
from src.app.models.simulation import Simulation
from src.app.models.society_result import SocietyResult
from src.app.models.evaluation_result import EvaluationResult
from src.app.models.conversation_log import ConversationLog
from src.app.services.society.population_generator import (
    generate_population,
    get_default_population_size,
    validate_population_size,
)

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
    count: int = Field(default_factory=get_default_population_size)
    seed: int | None = None


@router.post("/populations/generate")
async def generate_population_endpoint(
    body: PopulationGenerateRequest,
    session: AsyncSession = Depends(get_session),
):
    """人口生成をトリガーする。"""
    try:
        count = validate_population_size(body.count)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pop_id = str(uuid.uuid4())
    population = Population(
        id=pop_id,
        agent_count=count,
        generation_params={"count": count, "seed": body.seed},
        status="generating",
    )
    session.add(population)
    await session.commit()

    # 同期的に生成（小さいので高速）
    agents = await generate_population(pop_id, count, seed=body.seed)
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


@router.get("/simulations/{sim_id}/narrative")
async def get_narrative(
    sim_id: str,
    session: AsyncSession = Depends(get_session),
):
    """構造化ナラティブレポートを返す。"""
    result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "narrative")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="ナラティブレポートが見つかりません")

    return {
        "id": record.id,
        "simulation_id": record.simulation_id,
        "phase_data": record.phase_data,
        "created_at": record.created_at.isoformat(),
    }


@router.get("/simulations/{sim_id}/demographics")
async def get_demographics(
    sim_id: str,
    session: AsyncSession = Depends(get_session),
):
    """デモグラフィック・クロス分析結果を返す。"""
    result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "demographic_analysis")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="デモグラフィック分析結果が見つかりません")

    return {
        "id": record.id,
        "simulation_id": record.simulation_id,
        "phase_data": record.phase_data,
        "created_at": record.created_at.isoformat(),
    }


@router.get("/simulations/{sim_id}/propagation")
async def get_propagation(
    sim_id: str,
    session: AsyncSession = Depends(get_session),
):
    """ネットワーク伝播結果を返す（クラスタ、エコーチェンバー、タイムステップ履歴）。"""
    result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "network_propagation")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if not record:
        return {"phase_data": None}

    return {
        "id": record.id,
        "simulation_id": record.simulation_id,
        "phase_data": record.phase_data,
        "created_at": record.created_at.isoformat(),
    }


# =============================================================================
# ソーシャルグラフ & エージェント & 会話 API
# =============================================================================


async def _resolve_population_id(sim_id: str, session: AsyncSession) -> str:
    """シミュレーションから population_id を解決する。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="シミュレーションが見つかりません")
    if not sim.population_id:
        raise HTTPException(status_code=404, detail="このシミュレーションにはPopulationがありません")
    return sim.population_id


@router.get("/simulations/{sim_id}/social-graph")
async def get_social_graph(
    sim_id: str,
    session: AsyncSession = Depends(get_session),
):
    """ソーシャルグラフ（エージェントノード + SocialEdge）を返す。"""
    pop_id = await _resolve_population_id(sim_id, session)

    # activation 結果からエージェント情報を取得
    act_result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "activation")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    act_record = act_result.scalar_one_or_none()

    # activation の個別回答から agent_id → response のマップを作成
    response_map: dict[str, dict] = {}
    selected_agent_ids: list[str] = []
    if act_record and act_record.phase_data:
        for resp in act_record.phase_data.get("responses", []):
            aid = resp.get("agent_id", "")
            if aid:
                response_map[aid] = resp
                selected_agent_ids.append(aid)

    # 選抜済みエージェントのプロファイルを取得
    if selected_agent_ids:
        agents_result = await session.execute(
            select(AgentProfile).where(AgentProfile.id.in_(selected_agent_ids))
        )
        agents = agents_result.scalars().all()
    else:
        # フォールバック: population の全エージェント（最大200）
        agents_result = await session.execute(
            select(AgentProfile)
            .where(AgentProfile.population_id == pop_id)
            .order_by(AgentProfile.agent_index)
            .limit(200)
        )
        agents = agents_result.scalars().all()

    agent_id_set = {a.id for a in agents}

    # ソーシャルエッジを取得（両端がノードセットに含まれるもの）
    edges_result = await session.execute(
        select(SocialEdge).where(
            SocialEdge.population_id == pop_id,
            SocialEdge.agent_id.in_(agent_id_set),
            SocialEdge.target_id.in_(agent_id_set),
        )
    )
    edges = edges_result.scalars().all()

    # ノードを構築
    nodes = []
    for a in agents:
        demo = a.demographics or {}
        resp = response_map.get(a.id, {})
        nodes.append({
            "id": a.id,
            "agent_index": a.agent_index,
            "demographics": demo,
            "big_five": a.big_five or {},
            "values": a.values or {},
            "speech_style": a.speech_style or "",
            "stance": resp.get("stance", ""),
            "confidence": resp.get("confidence", 0),
            "reason": resp.get("reason", ""),
            "concern": resp.get("concern", ""),
            "priority": resp.get("priority", ""),
        })

    # エッジを構築
    edge_list = [
        {
            "id": e.id,
            "source": e.agent_id,
            "target": e.target_id,
            "relation_type": e.relation_type,
            "strength": e.strength,
        }
        for e in edges
    ]

    return {
        "nodes": nodes,
        "edges": edge_list,
        "population_id": pop_id,
    }


@router.get("/simulations/{sim_id}/agents")
async def get_agents(
    sim_id: str,
    stance: str | None = Query(None),
    region: str | None = Query(None),
    occupation: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """選抜済みエージェント一覧（activation 回答付き、フィルター対応）。"""
    pop_id = await _resolve_population_id(sim_id, session)

    # activation 結果を取得
    act_result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "activation")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    act_record = act_result.scalar_one_or_none()

    responses = act_record.phase_data.get("responses", []) if act_record and act_record.phase_data else []

    # フィルタリング
    filtered = responses
    if stance:
        filtered = [r for r in filtered if r.get("stance") == stance]

    # agent_id → response のマップ
    agent_ids = [r["agent_id"] for r in filtered if r.get("agent_id")]
    if not agent_ids:
        return {"agents": [], "total": 0, "page": page, "page_size": page_size}

    # エージェントプロファイルを取得
    agents_result = await session.execute(
        select(AgentProfile).where(AgentProfile.id.in_(agent_ids))
    )
    agents_db = {a.id: a for a in agents_result.scalars().all()}

    # region/occupation フィルター（DB取得後にフィルター）
    result_list = []
    for resp in filtered:
        aid = resp.get("agent_id", "")
        agent = agents_db.get(aid)
        if not agent:
            continue
        demo = agent.demographics or {}
        if region and demo.get("region") != region:
            continue
        if occupation and demo.get("occupation") != occupation:
            continue
        result_list.append({
            "id": agent.id,
            "agent_index": agent.agent_index,
            "demographics": demo,
            "big_five": agent.big_five or {},
            "stance": resp.get("stance", ""),
            "confidence": resp.get("confidence", 0),
            "reason": resp.get("reason", ""),
            "concern": resp.get("concern", ""),
            "priority": resp.get("priority", ""),
        })

    total = len(result_list)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "agents": result_list[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/simulations/{sim_id}/agents/{agent_id}")
async def get_agent_detail(
    sim_id: str,
    agent_id: str,
    session: AsyncSession = Depends(get_session),
):
    """エージェント詳細（プロファイル + activation回答 + meeting発言）。"""
    agent = await session.get(AgentProfile, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="エージェントが見つかりません")

    # activation 回答を取得
    act_result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "activation")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    act_record = act_result.scalar_one_or_none()

    activation_response = None
    if act_record and act_record.phase_data:
        for resp in act_record.phase_data.get("responses", []):
            if resp.get("agent_id") == agent_id:
                activation_response = resp
                break

    # meeting 発言を取得
    mtg_result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "meeting")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    mtg_record = mtg_result.scalar_one_or_none()

    meeting_contributions = []
    meeting_participant_info = None
    if mtg_record and mtg_record.phase_data:
        # 参加者情報から該当エージェントを探す
        for p in mtg_record.phase_data.get("participants", []):
            if p.get("agent_id") == agent_id:
                meeting_participant_info = p
                break

        # ラウンドから発言を抽出
        if meeting_participant_info:
            participant_idx = None
            for idx, p in enumerate(mtg_record.phase_data.get("participants", [])):
                if p.get("agent_id") == agent_id:
                    participant_idx = idx
                    break

            if participant_idx is not None:
                for round_args in mtg_record.phase_data.get("rounds", []):
                    for arg in round_args:
                        if arg.get("participant_index") == participant_idx:
                            meeting_contributions.append(arg)

    # ソーシャルコネクション
    connections_result = await session.execute(
        select(SocialEdge).where(
            SocialEdge.population_id == agent.population_id,
            (SocialEdge.agent_id == agent_id) | (SocialEdge.target_id == agent_id),
        )
    )
    connections = connections_result.scalars().all()

    return {
        "id": agent.id,
        "agent_index": agent.agent_index,
        "population_id": agent.population_id,
        "demographics": agent.demographics or {},
        "big_five": agent.big_five or {},
        "values": agent.values or {},
        "life_event": agent.life_event or "",
        "contradiction": agent.contradiction or "",
        "information_source": agent.information_source or "",
        "local_context": agent.local_context or "",
        "hidden_motivation": agent.hidden_motivation or "",
        "speech_style": agent.speech_style or "",
        "shock_sensitivity": agent.shock_sensitivity or {},
        "memory_summary": agent.memory_summary or "",
        "activation_response": activation_response,
        "meeting_participant": meeting_participant_info,
        "meeting_contributions": meeting_contributions,
        "connections": [
            {
                "id": c.id,
                "agent_id": c.agent_id,
                "target_id": c.target_id,
                "relation_type": c.relation_type,
                "strength": c.strength,
                "connected_to": c.target_id if c.agent_id == agent_id else c.agent_id,
            }
            for c in connections
        ],
    }


@router.get("/simulations/{sim_id}/transcript")
async def get_transcript(
    sim_id: str,
    phase: str | None = Query(None, description="activation | meeting | synthesis"),
    round_number: int | None = Query(None, alias="round"),
    session: AsyncSession = Depends(get_session),
):
    """シミュレーションの全会話トランスクリプトを時系列で返す。"""
    query = (
        select(ConversationLog)
        .where(ConversationLog.simulation_id == sim_id)
        .order_by(ConversationLog.phase, ConversationLog.round_number, ConversationLog.created_at)
    )
    if phase:
        query = query.where(ConversationLog.phase == phase)
    if round_number is not None:
        query = query.where(ConversationLog.round_number == round_number)

    result = await session.execute(query)
    logs = result.scalars().all()

    if not logs:
        raise HTTPException(status_code=404, detail="トランスクリプトが見つかりません")

    return {
        "simulation_id": sim_id,
        "total_entries": len(logs),
        "entries": [
            {
                "id": log.id,
                "phase": log.phase,
                "round_number": log.round_number,
                "participant_name": log.participant_name,
                "participant_role": log.participant_role,
                "content_text": log.content_text,
                "stance": log.stance,
                "stance_changed": log.stance_changed,
                "addressed_to": log.addressed_to,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
    }


@router.get("/simulations/{sim_id}/conversations")
async def get_conversations(
    sim_id: str,
    round_number: int | None = Query(None, alias="round"),
    participant_index: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Meeting ラウンド会話を返す（フィルター対応）。"""
    mtg_result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "meeting")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    mtg_record = mtg_result.scalar_one_or_none()
    if not mtg_record or not mtg_record.phase_data:
        raise HTTPException(status_code=404, detail="Meeting結果が見つかりません")

    phase = mtg_record.phase_data
    all_rounds = phase.get("rounds", [])
    participants = phase.get("participants", [])
    synthesis = phase.get("synthesis", {})

    # フィルター適用
    result_rounds = []
    for round_idx, round_args in enumerate(all_rounds):
        rn = round_idx + 1
        if round_number is not None and rn != round_number:
            continue

        filtered_args = round_args
        if participant_index is not None:
            filtered_args = [
                a for a in round_args if a.get("participant_index") == participant_index
            ]

        result_rounds.append({
            "round": rn,
            "arguments": filtered_args,
        })

    return {
        "rounds": result_rounds,
        "participants": participants,
        "synthesis": synthesis,
        "total_rounds": len(all_rounds),
    }
