"""EvaluationResult モデル: Society シミュレーションの評価メトリクス"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Float, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    simulation_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulations.id"))
    metric_name: Mapped[str] = mapped_column(String(50))
    # brier_score | kl_divergence | consistency | calibration | diversity
    score: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # single_llm | rule_based | swarm
    baseline_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
