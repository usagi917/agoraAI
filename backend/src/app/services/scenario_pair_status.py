"""Helpers for keeping ScenarioPair status in sync with child simulations."""

from __future__ import annotations

from src.app.models.scenario_pair import ScenarioPair
from src.app.models.simulation import Simulation

# ステータスのランク定義: 高いほど進んだ状態。
# refresh_scenario_pair_status はこのランクを使って後退（regression）を防ぐ。
# 例: completed(3) -> running(2) への書き戻しを防ぐ。
# completed と failed は同ランク: どちらも終端状態であり、
# リラン後に failed -> completed への復旧を可能にする。
_STATUS_RANK: dict[str, int] = {
    "created": 0,
    "queued": 1,
    "running": 2,
    "completed": 3,
    "failed": 3,
}


def derive_scenario_pair_status(simulation_statuses: list[str]) -> str:
    """Collapse child simulation statuses into a single pair status.

    queued は running と区別して保持する。
    ワーカーが死亡して永遠に "running" を報告する誤報を防ぐため、
    queued は queued として返す（running に折り畳まない）。
    """
    if not simulation_statuses:
        return "created"
    if any(status == "failed" for status in simulation_statuses):
        return "failed"
    if all(status == "completed" for status in simulation_statuses):
        return "completed"
    # running が1つでもあれば running
    if any(status == "running" for status in simulation_statuses):
        return "running"
    # queued が1つでもあれば queued（running に折り畳まない）
    if any(status == "queued" for status in simulation_statuses):
        return "queued"
    return "created"


async def refresh_scenario_pair_status(
    session,
    scenario_pair_id: str | None,
) -> ScenarioPair | None:
    """Update the stored ScenarioPair status from current simulation rows.

    楽観的ロック: 導出された新しいステータスが現在のステータスより低ランクなら
    更新しない。これにより completed -> running のような後退（regression）を防ぐ。
    """
    if not scenario_pair_id:
        return None

    pair = await session.get(ScenarioPair, scenario_pair_id)
    if not pair:
        return None

    simulation_statuses: list[str] = []
    for simulation_id in (pair.baseline_simulation_id, pair.intervention_simulation_id):
        if not simulation_id:
            continue
        simulation = await session.get(Simulation, simulation_id)
        if simulation:
            simulation_statuses.append(simulation.status)

    derived = derive_scenario_pair_status(simulation_statuses)

    # 楽観的ロック: 後退するなら更新しない
    current_rank = _STATUS_RANK.get(pair.status, 0)
    derived_rank = _STATUS_RANK.get(derived, 0)
    if derived_rank >= current_rank:
        pair.status = derived

    return pair
