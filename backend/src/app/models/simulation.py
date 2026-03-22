"""Simulation モデル: パイプライン型アーキテクチャの統合ファサード"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="pipeline")  # pipeline | single | swarm | hybrid | pm_board | society | society_first
    prompt_text: Mapped[str] = mapped_column(Text, default="")
    template_name: Mapped[str] = mapped_column(String(100), default="")
    execution_profile: Mapped[str] = mapped_column(String(20), default="standard")
    colony_count: Mapped[int] = mapped_column(Integer, default=1)
    deep_colony_count: Mapped[int] = mapped_column(Integer, default=0)  # hybrid 用
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error_message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("runs.id"), nullable=True)
    swarm_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("swarms.id"), nullable=True)
    population_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("populations.id"), nullable=True)
    pipeline_stage: Mapped[str] = mapped_column(String(20), default="pending")
    stage_progress: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
