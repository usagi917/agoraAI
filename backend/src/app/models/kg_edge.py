import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class KGEdge(Base):
    __tablename__ = "kg_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    source_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("kg_nodes.id"))
    target_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("kg_nodes.id"))
    relation_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_text: Mapped[str] = mapped_column(Text, default="")
    valid_from_round: Mapped[int] = mapped_column(Integer, default=0)
    valid_to_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
