import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class GraphDiff(Base):
    __tablename__ = "graph_diffs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    added_nodes: Mapped[dict] = mapped_column(JSON, default=list)
    updated_nodes: Mapped[dict] = mapped_column(JSON, default=list)
    removed_nodes: Mapped[dict] = mapped_column(JSON, default=list)
    added_edges: Mapped[dict] = mapped_column(JSON, default=list)
    updated_edges: Mapped[dict] = mapped_column(JSON, default=list)
    removed_edges: Mapped[dict] = mapped_column(JSON, default=list)
    highlights: Mapped[dict] = mapped_column(JSON, default=list)
    event_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
