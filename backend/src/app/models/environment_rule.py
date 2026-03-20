import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Float, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class EnvironmentRule(Base):
    __tablename__ = "environment_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    rule_type: Mapped[str] = mapped_column(String(50))  # trigger/constraint/periodic
    condition: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    probability: Mapped[float] = mapped_column(Float, default=1.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
