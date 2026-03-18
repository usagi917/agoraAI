import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Integer, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.database import Base


class Swarm(Base):
    __tablename__ = "swarms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    template_name: Mapped[str] = mapped_column(String(100))
    execution_profile: Mapped[str] = mapped_column(String(20), default="standard")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    colony_count: Mapped[int] = mapped_column(Integer, default=5)
    completed_colonies: Mapped[int] = mapped_column(Integer, default=0)
    total_rounds: Mapped[int] = mapped_column(Integer, default=4)
    diversity_mode: Mapped[str] = mapped_column(String(20), default="balanced")
    error_message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    colonies: Mapped[list["Colony"]] = relationship(back_populates="swarm", cascade="all, delete-orphan")


from src.app.models.colony import Colony  # noqa: E402, F401
