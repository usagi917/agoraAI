"""Validation リポジトリ"""

import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import utcnow_naive
from src.app.models.validation_record import ValidationRecord

# --- 精度指標のユーティリティ（service 層に依存しないよう自己完結） ---

STANCE_ORDER = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


def _brier_score_distributions(predicted: dict[str, float], actual: dict[str, float]) -> float:
    """2つの分布間の Brier Score を計算する。

    Σ(p_i - a_i)² where p_i = predicted, a_i = actual
    """
    all_keys = set(predicted.keys()) | set(actual.keys())
    return sum(
        (predicted.get(k, 0.0) - actual.get(k, 0.0)) ** 2
        for k in all_keys
    )


def _kl_divergence_symmetric(
    p: dict[str, float],
    q: dict[str, float],
    smoothing: float = 1e-6,
) -> float:
    """対称KL-divergence: (KL(p||q) + KL(q||p)) / 2。"""
    all_keys = set(p.keys()) | set(q.keys())
    p_smooth = {k: p.get(k, 0.0) + smoothing for k in all_keys}
    q_smooth = {k: q.get(k, 0.0) + smoothing for k in all_keys}
    p_total = sum(p_smooth.values())
    q_total = sum(q_smooth.values())
    p_norm = {k: v / p_total for k, v in p_smooth.items()}
    q_norm = {k: v / q_total for k, v in q_smooth.items()}
    kl_pq = sum(p_norm[k] * math.log(p_norm[k] / q_norm[k]) for k in all_keys)
    kl_qp = sum(q_norm[k] * math.log(q_norm[k] / p_norm[k]) for k in all_keys)
    return (kl_pq + kl_qp) / 2.0


def _earth_movers_distance(p: dict[str, float], q: dict[str, float]) -> float:
    """序数距離を考慮したEarth Mover's Distance。"""
    p_vals = [p.get(s, 0.0) for s in STANCE_ORDER]
    q_vals = [q.get(s, 0.0) for s in STANCE_ORDER]
    emd = 0.0
    cumulative = 0.0
    for i in range(len(STANCE_ORDER)):
        cumulative += p_vals[i] - q_vals[i]
        emd += abs(cumulative)
    return emd


class ValidationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(
        self,
        simulation_id: str,
        theme_text: str,
        theme_category: str,
        simulated_distribution: dict,
        calibrated_distribution: dict | None = None,
    ) -> ValidationRecord:
        record = ValidationRecord(
            simulation_id=simulation_id,
            theme_text=theme_text,
            theme_category=theme_category,
            simulated_distribution=simulated_distribution,
            calibrated_distribution=calibrated_distribution,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get(self, record_id: str) -> ValidationRecord | None:
        stmt = select(ValidationRecord).where(ValidationRecord.id == record_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_simulation(self, simulation_id: str) -> list[ValidationRecord]:
        stmt = select(ValidationRecord).where(
            ValidationRecord.simulation_id == simulation_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_category(self, theme_category: str) -> list[ValidationRecord]:
        stmt = select(ValidationRecord).where(
            ValidationRecord.theme_category == theme_category
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_validated(self) -> list[ValidationRecord]:
        stmt = select(ValidationRecord).where(
            ValidationRecord.validated_at.isnot(None)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def resolve(
        self,
        record_id: str,
        actual_distribution: dict,
        survey_source: str,
        survey_date: str,
    ) -> ValidationRecord:
        record = await self.get(record_id)
        if record is None:
            raise ValueError(f"ValidationRecord not found: {record_id}")

        record.actual_distribution = actual_distribution
        record.survey_source = survey_source
        record.survey_date = survey_date

        # 精度指標を自動算出
        sim_dist = record.simulated_distribution
        record.brier_score = _brier_score_distributions(sim_dist, actual_distribution)
        record.kl_divergence = _kl_divergence_symmetric(sim_dist, actual_distribution)
        record.emd = _earth_movers_distance(sim_dist, actual_distribution)
        record.validated_at = utcnow_naive()

        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def aggregate_by_category(
        self,
        theme_category: str | None = None,
    ) -> dict:
        stmt = select(ValidationRecord).where(
            ValidationRecord.validated_at.isnot(None)
        )
        if theme_category:
            stmt = stmt.where(ValidationRecord.theme_category == theme_category)

        result = await self.session.execute(stmt)
        records = list(result.scalars().all())

        if not records:
            return {"count": 0, "avg_brier": None, "avg_kl": None, "avg_emd": None}

        briers = [r.brier_score for r in records if r.brier_score is not None]
        kls = [r.kl_divergence for r in records if r.kl_divergence is not None]
        emds = [r.emd for r in records if r.emd is not None]

        return {
            "count": len(records),
            "avg_brier": sum(briers) / len(briers) if briers else None,
            "avg_kl": sum(kls) / len(kls) if kls else None,
            "avg_emd": sum(emds) / len(emds) if emds else None,
        }
