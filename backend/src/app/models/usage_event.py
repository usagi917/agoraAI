"""Anonymous product-usage events for short-lived demo analytics."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    event_name: Mapped[str] = mapped_column(String(50), index=True)
    visitor_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    simulation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("simulations.id"), nullable=True, index=True
    )
    path: Mapped[str] = mapped_column(String(255), default="")
    properties_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, index=True
    )
