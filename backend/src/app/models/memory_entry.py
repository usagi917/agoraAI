import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Float, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    agent_id: Mapped[str] = mapped_column(String(36))
    memory_type: Mapped[str] = mapped_column(String(20))  # episodic/semantic/procedural
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_round: Mapped[int] = mapped_column(Integer, default=0)
    is_reflection: Mapped[bool] = mapped_column(Boolean, default=False)
    reflection_level: Mapped[int] = mapped_column(Integer, default=0)
    source_memory_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
