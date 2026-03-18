"""エージェント間メッセージのDBモデル"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    channel_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sender_id: Mapped[str] = mapped_column(String(100))
    recipient_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # list of agent IDs
    message_type: Mapped[str] = mapped_column(String(20))  # say|propose|accept|reject|inform|request
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    in_reply_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
