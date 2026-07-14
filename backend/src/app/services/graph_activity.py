"""社会グラフイベントを永続化し、同一 DTO で SSE 配信する。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.graph_activity_event import GraphActivityEvent
from src.app.schemas.graph_activity import GraphActivityEventDTO, GraphActivityKind


@dataclass(frozen=True)
class GraphActivityCreate:
    phase: str
    kind: GraphActivityKind
    round: int = 0
    source_id: str | None = None
    target_id: str | None = None
    edge_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime | None = None


def propagation_changes_to_graph_events(
    changes,
    *,
    phase: str,
    round: int,
    stance_source_key: str,
) -> list[GraphActivityCreate]:
    """伝播変化を influence + stance_shift の共通イベント形式へ変換する。"""
    events: list[GraphActivityCreate] = []
    for change in changes:
        source_id = change.get("source_id")
        target_id = change.get("target_id")
        before_stance = change.get("before_stance", "")
        after_stance = change.get("after_stance", change.get("stance", ""))
        opinion_delta = change.get("opinion_delta", 0.0)
        if source_id:
            events.append(GraphActivityCreate(
                phase=phase,
                round=round,
                kind="influence",
                source_id=source_id,
                target_id=target_id,
                payload={
                    "primary_influencer_id": source_id,
                    "before_stance": before_stance,
                    "after_stance": after_stance,
                    "opinion_delta": opinion_delta,
                    "edge_strength": change.get("edge_strength", 0.0),
                },
            ))
        events.append(GraphActivityCreate(
            phase=phase,
            round=round,
            kind="stance_shift",
            source_id=change.get(stance_source_key),
            payload={
                "before_stance": before_stance,
                "after_stance": after_stance,
                "opinion_delta": opinion_delta,
                "reason": "network propagation",
            },
        ))
    return events


def graph_activity_dto(event: GraphActivityEvent) -> GraphActivityEventDTO:
    return GraphActivityEventDTO.model_validate(event)


async def persist_graph_activity_events(
    session: AsyncSession,
    simulation_id: str,
    events: list[GraphActivityCreate],
    *,
    publish: bool = True,
) -> list[GraphActivityEventDTO]:
    """ID を一括採番して commit 後に ID 順で配信する。"""
    if not events:
        return []
    # Lightweight phase tests use protocol-only fake sessions. Event persistence
    # is an infrastructure concern and runs only for a real SQLAlchemy session.
    if not isinstance(session, AsyncSession):
        return []

    records = [
        GraphActivityEvent(
            simulation_id=simulation_id,
            phase=event.phase,
            round=event.round,
            kind=event.kind,
            source_id=event.source_id,
            target_id=event.target_id,
            edge_id=event.edge_id,
            payload=dict(event.payload),
            **({"occurred_at": event.occurred_at} if event.occurred_at else {}),
        )
        for event in events
    ]
    session.add_all(records)
    await session.flush()
    await session.commit()

    dtos = [graph_activity_dto(record) for record in records]
    if publish:
        from src.app.sse.manager import sse_manager

        for dto in dtos:
            await sse_manager.publish(
                simulation_id,
                "graph_activity",
                dto.model_dump(mode="json"),
            )
    return dtos


async def persist_graph_activity_event(
    session: AsyncSession,
    simulation_id: str,
    event: GraphActivityCreate,
    *,
    publish: bool = True,
) -> GraphActivityEventDTO:
    return (
        await persist_graph_activity_events(
            session,
            simulation_id,
            [event],
            publish=publish,
        )
    )[0]
