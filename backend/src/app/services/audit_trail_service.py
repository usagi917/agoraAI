"""Audit Trail Service: シミュレーション中のエージェント行動・信念変化の監査ログ管理"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.audit_event import AuditEvent

logger = logging.getLogger(__name__)


async def record_event(
    session: AsyncSession,
    simulation_id: str,
    agent_id: str,
    agent_name: str,
    round_number: int,
    event_type: str,  # "belief_change" | "opinion_shift" | "action"
    before_state: dict,
    after_state: dict,
    reasoning: str,
) -> AuditEvent:
    """Record an audit event to the database."""
    event = AuditEvent(
        simulation_id=simulation_id,
        agent_id=agent_id,
        agent_name=agent_name,
        round_number=round_number,
        event_type=event_type,
        before_state=before_state,
        after_state=after_state,
        reasoning=reasoning,
    )
    session.add(event)
    await session.flush()
    return event


async def get_audit_trail(
    session: AsyncSession,
    simulation_id: str,
    agent_id: str | None = None,
    event_type: str | None = None,
) -> list[AuditEvent]:
    """Query audit events with optional filters."""
    stmt = select(AuditEvent).where(AuditEvent.simulation_id == simulation_id)
    if agent_id is not None:
        stmt = stmt.where(AuditEvent.agent_id == agent_id)
    if event_type is not None:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    stmt = stmt.order_by(AuditEvent.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_opinion_shifts(
    session: AsyncSession,
    simulation_id: str,
) -> list[AuditEvent]:
    """Get only opinion_shift events for a simulation."""
    return await get_audit_trail(session, simulation_id, event_type="opinion_shift")


def detect_opinion_shift(before_beliefs: dict, after_beliefs: dict) -> bool:
    """Detect if beliefs changed significantly enough to count as an opinion shift.

    Compare before and after belief states.
    Return True if there's a meaningful change.
    """
    if not before_beliefs and not after_beliefs:
        return False
    if not before_beliefs or not after_beliefs:
        return True

    # 全キーの和集合を比較
    all_keys = set(before_beliefs.keys()) | set(after_beliefs.keys())
    for key in all_keys:
        before_val = before_beliefs.get(key)
        after_val = after_beliefs.get(key)
        if before_val != after_val:
            return True
    return False
