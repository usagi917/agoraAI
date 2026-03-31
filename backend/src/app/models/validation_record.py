"""ValidationRecord モデル: シミュレーション結果と実世論調査の照合記録"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Float, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class ValidationRecord(Base):
    __tablename__ = "validation_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    simulation_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulations.id"))
    theme_text: Mapped[str] = mapped_column(String(200))
    theme_category: Mapped[str] = mapped_column(String(50))
    simulated_distribution: Mapped[dict] = mapped_column(JSON)
    calibrated_distribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actual_distribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    survey_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    survey_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    brier_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    kl_divergence: Mapped[float | None] = mapped_column(Float, nullable=True)
    emd: Mapped[float | None] = mapped_column(Float, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
