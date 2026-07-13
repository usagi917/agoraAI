"""Durable per-agent outputs for resumable large population activation."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class AgentActivationResult(Base):
    __tablename__ = "agent_activation_results"
    __table_args__ = (
        UniqueConstraint(
            "simulation_id",
            "agent_id",
            "run_seed",
            "stage",
            "round_number",
            "provider",
            name="uq_agent_activation_checkpoint",
        ),
        Index("ix_agent_activation_sim_stage_status", "simulation_id", "stage", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    simulation_id: Mapped[str] = mapped_column(String(36), index=True)
    population_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    agent_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_index: Mapped[int] = mapped_column(Integer, default=0)
    run_seed: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(30))
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(150), default="")
    status: Mapped[str] = mapped_column(String(20), default="success")
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    stance: Mapped[str] = mapped_column(String(30), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )
