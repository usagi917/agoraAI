"""ValidationRecord モデル: シミュレーション結果と実世論調査の照合記録"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
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
    # Step 2: 新カラム（validation 基盤 / theme_category 拡張）
    jsd: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    theme_category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    theme_category_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    survey_manifest_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
