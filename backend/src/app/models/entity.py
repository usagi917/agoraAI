import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    label: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, default="")
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)
    stance: Mapped[str] = mapped_column(String(100), default="")
    activity_score: Mapped[float] = mapped_column(Float, default=0.5)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="active")
    group: Mapped[str] = mapped_column(String(100), default="")
    last_updated_round: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
