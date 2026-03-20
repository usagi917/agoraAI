import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Integer, Float, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.database import Base


class Colony(Base):
    __tablename__ = "colonies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    swarm_id: Mapped[str] = mapped_column(String(36), ForeignKey("swarms.id"))
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("runs.id"), nullable=True)
    colony_index: Mapped[int] = mapped_column(Integer)
    perspective_id: Mapped[str] = mapped_column(String(50))
    perspective_label: Mapped[str] = mapped_column(String(100), default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.5)
    prompt_variant: Mapped[int] = mapped_column(Integer, default=0)
    adversarial: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    total_rounds: Mapped[int] = mapped_column(Integer, default=4)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    result_data: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    swarm: Mapped["Swarm"] = relationship(back_populates="colonies")


from src.app.models.swarm import Swarm  # noqa: E402, F401
