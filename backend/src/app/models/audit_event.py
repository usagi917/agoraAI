"""AuditEvent モデル: シミュレーション中のエージェント行動・信念変化の監査ログ"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    simulation_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulations.id"))
    agent_id: Mapped[str] = mapped_column(String(36))
    agent_name: Mapped[str] = mapped_column(String(100))
    round_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(30))  # belief_change | opinion_shift | action
    before_state: Mapped[dict] = mapped_column(JSON, default=dict)
    after_state: Mapped[dict] = mapped_column(JSON, default=dict)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
