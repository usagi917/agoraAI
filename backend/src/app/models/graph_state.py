import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class GraphState(Base):
    __tablename__ = "graph_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    nodes: Mapped[dict] = mapped_column(JSON, default=list)
    edges: Mapped[dict] = mapped_column(JSON, default=list)
    focus_entities: Mapped[dict] = mapped_column(JSON, default=list)
    highlights: Mapped[dict] = mapped_column(JSON, default=list)
    event_refs: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
