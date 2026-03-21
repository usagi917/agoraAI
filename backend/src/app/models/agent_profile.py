"""AgentProfile モデル: 住民プロフィール（人口統計・性格・価値観・認知特性）"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Text, JSON, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    population_id: Mapped[str] = mapped_column(String(36), ForeignKey("populations.id"))
    agent_index: Mapped[int] = mapped_column(Integer)

    # 人口統計
    demographics: Mapped[dict] = mapped_column(JSON, default=dict)
    # {age, gender, occupation, region, income_bracket, education}

    # Big Five パーソナリティ (各 0-1)
    big_five: Mapped[dict] = mapped_column(JSON, default=dict)
    # {O, C, E, A, N}

    # 価値観リスト + 重み
    values: Mapped[dict] = mapped_column(JSON, default=dict)

    # 生活背景・矛盾・情報源
    life_event: Mapped[str] = mapped_column(Text, default="")
    contradiction: Mapped[str] = mapped_column(Text, default="")
    information_source: Mapped[str] = mapped_column(Text, default="")

    # ローカルコンテキスト・隠された動機・発話スタイル
    local_context: Mapped[str] = mapped_column(Text, default="")
    hidden_motivation: Mapped[str] = mapped_column(Text, default="")
    speech_style: Mapped[str] = mapped_column(Text, default="")

    # トピック別ショック感応度 {topic: 0-1}
    shock_sensitivity: Mapped[dict] = mapped_column(JSON, default=dict)

    # LLMバックエンド割当
    llm_backend: Mapped[str] = mapped_column(String(50), default="openai")

    # 記憶要約（Phase 3 で活用）
    memory_summary: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
