"""ConversationLog モデル: 議論の全発言を記録するトランスクリプト"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Integer, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive

CONVERSATION_LOG_PHASE_MAX_LENGTH = 20
CONVERSATION_LOG_PARTICIPANT_NAME_MAX_LENGTH = 200
CONVERSATION_LOG_PARTICIPANT_ROLE_MAX_LENGTH = 64
CONVERSATION_LOG_STANCE_MAX_LENGTH = 255
CONVERSATION_LOG_ADDRESSED_TO_MAX_LENGTH = 200


class ConversationLog(Base):
    __tablename__ = "conversation_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    simulation_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulations.id"), index=True)
    phase: Mapped[str] = mapped_column(String(CONVERSATION_LOG_PHASE_MAX_LENGTH))  # activation | meeting | synthesis
    round_number: Mapped[int] = mapped_column(Integer, default=0)  # 0 for activation, 1-3 for meeting
    participant_name: Mapped[str] = mapped_column(String(CONVERSATION_LOG_PARTICIPANT_NAME_MAX_LENGTH), default="")
    participant_role: Mapped[str] = mapped_column(String(CONVERSATION_LOG_PARTICIPANT_ROLE_MAX_LENGTH), default="")
    participant_index: Mapped[int] = mapped_column(Integer, default=-1)
    content_text: Mapped[str] = mapped_column(Text, default="")  # Full natural-language text
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)  # Original structured response
    stance: Mapped[str] = mapped_column(String(CONVERSATION_LOG_STANCE_MAX_LENGTH), default="")
    stance_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    addressed_to: Mapped[str] = mapped_column(String(CONVERSATION_LOG_ADDRESSED_TO_MAX_LENGTH), default="")  # Who this response addresses
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
