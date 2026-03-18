import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class CalibrationData(Base):
    __tablename__ = "calibration_data"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    swarm_id: Mapped[str] = mapped_column(String(36), ForeignKey("swarms.id"))
    scenario_description: Mapped[str] = mapped_column(Text)
    predicted_probability: Mapped[float] = mapped_column(Float)
    actual_outcome: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback_text: Mapped[str] = mapped_column(Text, default="")
    brier_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
