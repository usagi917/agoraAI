import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class OutcomeClaim(Base):
    __tablename__ = "outcome_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    swarm_id: Mapped[str] = mapped_column(String(36), ForeignKey("swarms.id"))
    colony_id: Mapped[str] = mapped_column(String(36), ForeignKey("colonies.id"))
    claim_text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(50), default="prediction")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence: Mapped[str] = mapped_column(Text, default="")
    entities_involved: Mapped[dict] = mapped_column(JSON, default=list)
    embedding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cluster_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("claim_clusters.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
