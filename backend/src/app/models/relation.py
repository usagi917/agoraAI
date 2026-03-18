import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class Relation(Base):
    __tablename__ = "relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    source_entity_id: Mapped[str] = mapped_column(String(36))
    target_entity_id: Mapped[str] = mapped_column(String(36))
    relation_type: Mapped[str] = mapped_column(String(100))
    weight: Mapped[float] = mapped_column(Float, default=0.5)
    direction: Mapped[str] = mapped_column(String(20), default="directed")
    status: Mapped[str] = mapped_column(String(50), default="active")
    last_updated_round: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
