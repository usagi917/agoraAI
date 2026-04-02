"""Simulation モデル: パイプライン型アーキテクチャの統合ファサード"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive

# --- プリセット定義 ---

PRESETS: dict[str, list[str]] = {
    "quick": ["society_pulse", "synthesis"],
    "standard": ["society_pulse", "council", "synthesis"],
    "deep": ["society_pulse", "multi_perspective", "council", "pm_analysis", "synthesis"],
    "research": ["society_pulse", "issue_mining", "multi_perspective", "intervention", "synthesis"],
}

VALID_PRESETS = set(PRESETS.keys()) | {"baseline"}

MODE_ALIASES: dict[str, str] = {
    "pipeline": "deep",
    "swarm": "deep",
    "hybrid": "deep",
    "pm_board": "deep",
    "single": "quick",
    "society": "standard",
    "society_first": "research",
    "meta_simulation": "research",
    "unified": "standard",
}


def normalize_mode(mode: str) -> str:
    """モード名を正規化する。旧モードは新プリセットにマップ。"""
    if mode in VALID_PRESETS:
        return mode
    if mode in MODE_ALIASES:
        return MODE_ALIASES[mode]
    raise ValueError(f"Unknown mode: {mode}. Valid: {VALID_PRESETS}")


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="pipeline")  # pipeline | meta_simulation | single | swarm | hybrid | pm_board | society | society_first | unified
    prompt_text: Mapped[str] = mapped_column(Text, default="")
    template_name: Mapped[str] = mapped_column(String(100), default="")
    execution_profile: Mapped[str] = mapped_column(String(20), default="standard")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error_message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("runs.id"), nullable=True)
    population_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("populations.id"), nullable=True)
    pipeline_stage: Mapped[str] = mapped_column(String(20), default="pending")
    stage_progress: Mapped[dict] = mapped_column(JSON, default=dict)

    # 学術再現性
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    # Decision Laboratory
    scenario_pair_id: Mapped[str | None] = mapped_column(String(36), default=None, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
