"""Privacy-conscious anonymous usage analytics endpoints."""

import os
import secrets
from collections import Counter
from datetime import UTC, datetime
from statistics import median
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.models.simulation import Simulation
from src.app.models.usage_event import UsageEvent

router = APIRouter()

UsageEventName = Literal[
    "session_started",
    "page_view",
    "result_viewed",
    "simulation_started",
    "simulation_completed",
    "simulation_failed",
]

ALLOWED_PROPERTY_KEYS = {
    "route_name",
    "mode",
    "template_name",
    "execution_profile",
    "input_method",
    "has_documents",
    "document_count",
}
IDENTITY_PATTERN = r"^[a-zA-Z0-9_-]{8,64}$"


class UsageEventCreate(BaseModel):
    event_name: UsageEventName
    visitor_id: str = Field(pattern=IDENTITY_PATTERN)
    session_id: str = Field(pattern=IDENTITY_PATTERN)
    simulation_id: str | None = Field(
        default=None,
        min_length=36,
        max_length=36,
        pattern=r"^[a-fA-F0-9-]{36}$",
    )
    path: str = Field(default="", max_length=255)
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        return value.split("?", 1)[0]

    @field_validator("properties")
    @classmethod
    def reject_unapproved_properties(
        cls,
        value: dict[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        unknown_keys = set(value) - ALLOWED_PROPERTY_KEYS
        if unknown_keys:
            names = ", ".join(sorted(unknown_keys))
            raise ValueError(f"Unsupported analytics properties: {names}")
        return value


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _analytics_context(simulation: Simulation) -> dict[str, str]:
    metadata = simulation.metadata_json if isinstance(simulation.metadata_json, dict) else {}
    analytics = metadata.get("analytics")
    if not isinstance(analytics, dict):
        return {}
    return {
        key: str(value)
        for key, value in analytics.items()
        if key in {"visitor_id", "session_id", "input_method"} and value
    }


@router.post("/events", status_code=204)
async def create_usage_event(
    body: UsageEventCreate,
    session: AsyncSession = Depends(get_session),
) -> Response:
    event = UsageEvent(
        event_name=body.event_name,
        visitor_id=body.visitor_id,
        session_id=body.session_id,
        simulation_id=body.simulation_id,
        path=body.path,
        properties_json=body.properties,
    )
    session.add(event)
    await session.commit()
    return Response(status_code=204)


@router.get("/summary")
async def get_usage_summary(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    x_analytics_token: str | None = Header(default=None, alias="X-Analytics-Token"),
    session: AsyncSession = Depends(get_session),
):
    expected_token = os.environ.get("ANALYTICS_ADMIN_TOKEN", "")
    if not expected_token:
        raise HTTPException(status_code=503, detail="Analytics summary is not configured")
    if not x_analytics_token or not secrets.compare_digest(x_analytics_token, expected_token):
        raise HTTPException(status_code=403, detail="Invalid analytics token")

    start_at = _utc_naive(start)
    end_at = _utc_naive(end)

    event_query = select(UsageEvent)
    simulation_query = select(Simulation)
    if start_at is not None:
        event_query = event_query.where(UsageEvent.created_at >= start_at)
        simulation_query = simulation_query.where(Simulation.created_at >= start_at)
    if end_at is not None:
        event_query = event_query.where(UsageEvent.created_at < end_at)
        simulation_query = simulation_query.where(Simulation.created_at < end_at)

    events = (await session.execute(event_query)).scalars().all()
    simulations = (await session.execute(simulation_query)).scalars().all()

    visitor_ids = {event.visitor_id for event in events}
    session_ids = {event.session_id for event in events}
    by_input_method: Counter[str] = Counter()
    for simulation in simulations:
        analytics = _analytics_context(simulation)
        if analytics.get("visitor_id"):
            visitor_ids.add(analytics["visitor_id"])
        if analytics.get("session_id"):
            session_ids.add(analytics["session_id"])
        if analytics.get("input_method"):
            by_input_method[analytics["input_method"]] += 1

    event_counts = Counter(event.event_name for event in events)
    path_counts = Counter(event.path for event in events if event.path)
    status_counts = Counter(simulation.status for simulation in simulations)
    by_mode = Counter(simulation.mode for simulation in simulations)
    by_template = Counter(
        simulation.template_name or "未選択" for simulation in simulations
    )
    durations = [
        (simulation.completed_at - simulation.started_at).total_seconds()
        for simulation in simulations
        if simulation.started_at is not None and simulation.completed_at is not None
    ]
    total_simulations = len(simulations)
    completed_simulations = status_counts["completed"]
    simulation_details = []
    for simulation in sorted(simulations, key=lambda item: item.created_at, reverse=True)[:200]:
        analytics = _analytics_context(simulation)
        duration_seconds = None
        if simulation.started_at is not None and simulation.completed_at is not None:
            duration_seconds = round(
                (simulation.completed_at - simulation.started_at).total_seconds(),
                1,
            )
        simulation_details.append(
            {
                "id": simulation.id,
                "created_at": simulation.created_at.isoformat(),
                "status": simulation.status,
                "mode": simulation.mode,
                "template_name": simulation.template_name,
                "input_method": analytics.get("input_method", "unknown"),
                "duration_seconds": duration_seconds,
                "prompt_preview": simulation.prompt_text[:500],
            }
        )

    return {
        "window": {
            "start": start_at.isoformat() if start_at else None,
            "end": end_at.isoformat() if end_at else None,
        },
        "unique_visitors": len(visitor_ids),
        "sessions": len(session_ids),
        "event_counts": dict(sorted(event_counts.items())),
        "top_paths": [
            {"path": path, "count": count}
            for path, count in sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ],
        "simulations": {
            "total": total_simulations,
            "completed": completed_simulations,
            "failed": status_counts["failed"],
            "running": status_counts["running"],
            "queued": status_counts["queued"],
            "completion_rate": (
                round(completed_simulations / total_simulations, 4)
                if total_simulations
                else 0.0
            ),
            "median_duration_seconds": round(median(durations), 1) if durations else None,
        },
        "by_mode": dict(sorted(by_mode.items())),
        "by_template": dict(sorted(by_template.items())),
        "by_input_method": dict(sorted(by_input_method.items())),
        "simulation_details": simulation_details,
    }
