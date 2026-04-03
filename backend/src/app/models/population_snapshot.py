"""PopulationSnapshot モデル: エージェント人口のスナップショット（再現性用）"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class PopulationSnapshot(Base):
    __tablename__ = "population_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    population_id: Mapped[str] = mapped_column(String(36), ForeignKey("populations.id"))
    agent_profiles_json: Mapped[dict] = mapped_column(JSON, default=dict)
    relationships_json: Mapped[dict] = mapped_column(JSON, default=dict)
    initial_beliefs_json: Mapped[dict] = mapped_column(JSON, default=dict)
    seed: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
