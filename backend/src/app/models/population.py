"""Population モデル: エージェント人口の世代管理"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class Population(Base):
    __tablename__ = "populations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("populations.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    agent_count: Mapped[int] = mapped_column(Integer, default=1000)
    generation_params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="generating")  # generating | ready | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
