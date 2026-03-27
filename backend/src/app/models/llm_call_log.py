"""LLM呼び出しログモデル: 全LLM呼び出しの記録（学術再現性用）"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Integer, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    simulation_id: Mapped[str] = mapped_column(String(36), index=True)
    task_name: Mapped[str] = mapped_column(String(50))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))

    # トークン使用量
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # パフォーマンス
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    # 再現性パラメータ
    temperature: Mapped[float] = mapped_column(Float, default=0.5)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    # ハッシュ（軽量トレーサビリティ）
    system_prompt_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
    user_prompt_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
    response_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )

    # フルテキスト（オプション、デバッグ用）
    full_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    full_response: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive
    )
