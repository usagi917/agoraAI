"""Checkpoint persistence for chunked per-agent activation."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.agent_activation_result import AgentActivationResult


async def persist_activation_chunk(
    session: AsyncSession,
    *,
    simulation_id: str,
    population_id: str,
    stage: str,
    run_seed: int | None,
    records: list[dict],
    round_number: int = 0,
) -> None:
    """Upsert one completed chunk and commit it as a resume checkpoint."""
    if not records:
        return
    seed = int(run_seed or 0)
    agent_ids = [str(record["agent_id"]) for record in records]
    providers = {str(record.get("provider") or "unknown") for record in records}
    statement = select(AgentActivationResult).where(
        AgentActivationResult.simulation_id == simulation_id,
        AgentActivationResult.stage == stage,
        AgentActivationResult.run_seed == seed,
        AgentActivationResult.round_number == round_number,
        AgentActivationResult.agent_id.in_(agent_ids),
        AgentActivationResult.provider.in_(providers),
    )
    existing_rows = list((await session.scalars(statement)).all())
    existing = {(row.agent_id, row.provider): row for row in existing_rows}

    for record in records:
        provider = str(record.get("provider") or "unknown")
        response = dict(record.get("response") or {})
        usage = dict(record.get("usage") or {})
        failed = bool(response.get("_failed") or usage.get("_failed"))
        values = {
            "population_id": population_id,
            "agent_index": int(record.get("agent_index", 0) or 0),
            "model": str(record.get("model") or usage.get("model") or ""),
            "status": "failed" if failed else "success",
            "response_json": response,
            "stance": str(response.get("stance") or ""),
            "confidence": float(response.get("confidence", 0.0) or 0.0),
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "cost_usd": float(record.get("cost_usd", 0.0) or 0.0),
            "error_text": str(response.get("_error_msg") or record.get("error_text") or ""),
        }
        key = (str(record["agent_id"]), provider)
        row = existing.get(key)
        if row is None:
            row = AgentActivationResult(
                simulation_id=simulation_id,
                agent_id=key[0],
                run_seed=seed,
                stage=stage,
                round_number=round_number,
                provider=provider,
                **values,
            )
            session.add(row)
            existing[key] = row
        else:
            for name, value in values.items():
                setattr(row, name, value)
    await session.commit()


async def load_completed_responses(
    session: AsyncSession,
    *,
    simulation_id: str,
    stage: str,
    run_seed: int | None,
    provider: str,
) -> dict[str, dict]:
    statement = select(AgentActivationResult).where(
        AgentActivationResult.simulation_id == simulation_id,
        AgentActivationResult.stage == stage,
        AgentActivationResult.run_seed == int(run_seed or 0),
        AgentActivationResult.provider == provider,
        AgentActivationResult.status == "success",
    )
    rows = (await session.scalars(statement)).all()
    return {row.agent_id: dict(row.response_json or {}) for row in rows}


async def load_completed_response_rows(
    session: AsyncSession,
    *,
    simulation_id: str,
    stage: str,
    limit: int | None = None,
    agent_ids: list[str] | None = None,
) -> list[AgentActivationResult]:
    """完了済みステージを住民順で返す。フェーズ再開時の復元に使う。"""
    statement = select(AgentActivationResult).where(
        AgentActivationResult.simulation_id == simulation_id,
        AgentActivationResult.stage == stage,
        AgentActivationResult.status == "success",
    )
    if agent_ids is not None:
        if not agent_ids:
            return []
        statement = statement.where(AgentActivationResult.agent_id.in_(agent_ids))
    statement = statement.order_by(
        AgentActivationResult.agent_index,
        AgentActivationResult.agent_id,
    )
    if limit is not None:
        statement = statement.limit(max(0, limit))
    return list((await session.scalars(statement)).all())


async def load_preferred_response_rows(
    session: AsyncSession,
    *,
    simulation_id: str,
    stages: tuple[str, ...] = ("social_final", "local_initial"),
    limit: int | None = None,
    agent_ids: list[str] | None = None,
) -> list[AgentActivationResult]:
    """住民ごとに新しい意味論ステージを優先し、不足分は前段から補う。"""
    preferred_by_agent: dict[str, AgentActivationResult] = {}
    for stage in stages:
        rows = await load_completed_response_rows(
            session,
            simulation_id=simulation_id,
            stage=stage,
            limit=limit,
            agent_ids=agent_ids,
        )
        for row in rows:
            preferred_by_agent.setdefault(row.agent_id, row)

    ordered = sorted(
        preferred_by_agent.values(),
        key=lambda row: (row.agent_index, row.agent_id),
    )
    if limit is not None:
        return ordered[: max(0, limit)]
    return ordered


async def activation_stage_counts(
    session: AsyncSession, simulation_id: str
) -> dict[str, dict[str, int]]:
    rows = (
        await session.scalars(
            select(AgentActivationResult).where(
                AgentActivationResult.simulation_id == simulation_id
            )
        )
    ).all()
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        counts[row.stage][row.status] += 1
    return {stage: dict(statuses) for stage, statuses in counts.items()}
