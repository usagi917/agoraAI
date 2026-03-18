import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class EvaluationScore(Base):
    __tablename__ = "evaluation_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    goal_completion: Mapped[float] = mapped_column(Float, default=0.0)
    relationship_maintenance: Mapped[float] = mapped_column(Float, default=0.0)
    information_management: Mapped[float] = mapped_column(Float, default=0.0)
    social_norm_adherence: Mapped[float] = mapped_column(Float, default=0.0)
    behavioral_consistency: Mapped[float] = mapped_column(Float, default=0.0)
    causal_plausibility: Mapped[float] = mapped_column(Float, default=0.0)
    emergent_complexity: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
