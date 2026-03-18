import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class AgentState(Base):
    __tablename__ = "agent_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    agent_id: Mapped[str] = mapped_column(String(36))
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    beliefs: Mapped[dict] = mapped_column(JSON, default=list)
    desires: Mapped[dict] = mapped_column(JSON, default=list)
    intentions: Mapped[dict] = mapped_column(JSON, default=list)
    trust_map: Mapped[dict] = mapped_column(JSON, default=dict)
    mental_models: Mapped[dict] = mapped_column(JSON, default=dict)
    action_taken: Mapped[str] = mapped_column(Text, default="")
    reasoning_chain: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
