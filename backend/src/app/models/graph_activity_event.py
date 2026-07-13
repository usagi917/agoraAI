"""社会グラフのライブ表示と再生に使う永続イベント。"""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class GraphActivityEvent(Base):
    __tablename__ = "graph_activity_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('phase_changed', 'node_status', 'dialogue', 'influence', "
            "'stance_shift', 'relationship_changed')",
            name="ck_graph_activity_events_kind",
        ),
        Index(
            "ix_graph_activity_events_simulation_cursor",
            "simulation_id",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    phase: Mapped[str] = mapped_column(String(50), nullable=False)
    round: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    edge_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
