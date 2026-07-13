"""永続社会グラフイベントの公開 DTO。"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

GraphActivityKind = Literal[
    "phase_changed",
    "node_status",
    "dialogue",
    "influence",
    "stance_shift",
    "relationship_changed",
]


class GraphActivityEventDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    simulation_id: str
    occurred_at: datetime
    phase: str
    round: int = 0
    kind: GraphActivityKind
    source_id: str | None = None
    target_id: str | None = None
    edge_id: str | None = None
    payload: dict = Field(default_factory=dict)

    @field_serializer("occurred_at")
    def serialize_occurred_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
