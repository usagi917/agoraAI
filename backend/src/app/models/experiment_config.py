"""実験設定スナップショットモデル: 再現性のための設定記録"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive


class ExperimentConfig(Base):
    __tablename__ = "experiment_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    simulation_id: Mapped[str] = mapped_column(String(36), index=True)

    # YAML設定スナップショット
    models_yaml: Mapped[dict] = mapped_column(JSON, default=dict)
    cognitive_yaml: Mapped[dict] = mapped_column(JSON, default=dict)
    graphrag_yaml: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_providers_yaml: Mapped[dict] = mapped_column(JSON, default=dict)

    # 環境情報
    python_packages: Mapped[dict] = mapped_column(JSON, default=dict)
    git_commit_hash: Mapped[str | None] = mapped_column(
        String(40), nullable=True, default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive
    )
