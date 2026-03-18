"""校正エンジン: Brier score による予測精度の評価"""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.calibration_data import CalibrationData

logger = logging.getLogger(__name__)


def brier_score(predicted: float, actual: float) -> float:
    """Brier score を計算する。0 = 完全な予測、1 = 最悪の予測。"""
    return (predicted - actual) ** 2


async def record_feedback(
    session: AsyncSession,
    swarm_id: str,
    scenario_description: str,
    predicted_probability: float,
    actual_outcome: float,
    feedback_text: str = "",
) -> dict:
    """予測結果に対するフィードバックを記録し、Brier score を計算する。"""
    score = brier_score(predicted_probability, actual_outcome)

    calibration = CalibrationData(
        swarm_id=swarm_id,
        scenario_description=scenario_description,
        predicted_probability=predicted_probability,
        actual_outcome=actual_outcome,
        feedback_text=feedback_text,
        brier_score=score,
        resolved_at=datetime.utcnow(),
    )
    session.add(calibration)
    await session.flush()

    return {
        "brier_score": round(score, 4),
        "predicted": predicted_probability,
        "actual": actual_outcome,
        "calibration_id": calibration.id,
    }


