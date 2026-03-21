"""SocialEdge モデル: 住民間の社会的関係"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class SocialEdge(Base):
    __tablename__ = "social_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    population_id: Mapped[str] = mapped_column(String(36), ForeignKey("populations.id"))
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_profiles.id"))
    target_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_profiles.id"))
    relation_type: Mapped[str] = mapped_column(String(30), default="acquaintance")
    # friend | family | colleague | neighbor | acquaintance
    strength: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
