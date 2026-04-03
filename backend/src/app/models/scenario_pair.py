"""ScenarioPair モデル: ベースライン vs 介入シミュレーションのペア"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class ScenarioPair(Base):
    __tablename__ = "scenario_pairs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    population_snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("population_snapshots.id"))
    baseline_simulation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("simulations.id"), nullable=True)
    intervention_simulation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("simulations.id"), nullable=True)
    intervention_params: Mapped[dict] = mapped_column(JSON, default=dict)
    decision_context: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="created")  # created | running | completed | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
