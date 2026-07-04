"""SocietyResult モデル: Society シミュレーションのレイヤー別結果"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base, utcnow_naive

SOCIETY_RESULT_LAYER_MAX_LENGTH = 50


class SocietyResult(Base):
    __tablename__ = "society_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    simulation_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulations.id"))
    population_id: Mapped[str] = mapped_column(String(36), ForeignKey("populations.id"))
    layer: Mapped[str] = mapped_column(String(SOCIETY_RESULT_LAYER_MAX_LENGTH))  # activation | meeting | evaluation | population_propagation
    phase_data: Mapped[dict] = mapped_column(JSON, default=dict)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
