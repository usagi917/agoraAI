import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class KGNode(Base):
    __tablename__ = "kg_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    label: Mapped[str] = mapped_column(String(255))
    node_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, default="")
    aliases: Mapped[dict] = mapped_column(JSON, default=list)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    community_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
