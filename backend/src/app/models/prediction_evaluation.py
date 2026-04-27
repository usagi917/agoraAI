"""PredictionEvaluation model: cross-type prediction validation records."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class PredictionEvaluation(Base):
    __tablename__ = "prediction_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    simulation_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulations.id"))
    prediction_type: Mapped[str] = mapped_column(String(30))
    theme_category: Mapped[str] = mapped_column(String(50), default="")
    horizon: Mapped[str] = mapped_column(String(50), default="")
    predicted_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    actual_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(200), default="")
    primary_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
