"""Unified Orchestrator: 3フェーズ統合シミュレーション

Society Pulse → Council Deliberation → Synthesis の3フェーズを順に実行し、
Decision Brief 付きの統合レポートを生成する。
"""

import logging
from datetime import datetime, timezone

from src.app.database import async_session
from src.app.models.simulation import Simulation
from src.app.services.phases.society_pulse import run_society_pulse
from src.app.services.phases.council_deliberation import run_council
from src.app.services.phases.synthesis import run_synthesis
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def run_unified(simulation_id: str) -> None:
    """Unified モードのメインオーケストレーション。

    1つの async_session を開き、3フェーズに渡す。
    各フェーズ完了時にチェックポイント保存（session.commit）。
    """
    logger.info("Starting unified simulation %s", simulation_id)

    async with async_session() as session:
        sim = await session.get(Simulation, simulation_id)
        if not sim:
            logger.error("Simulation %s not found", simulation_id)
            return

        theme = sim.prompt_text

        try:
            # === Phase 1: Society Pulse ===
            await sse_manager.publish(simulation_id, "unified_phase_changed", {
                "phase": "society_pulse",
                "index": 1,
                "total": 3,
            })

            pulse = await run_society_pulse(session, sim, theme)

            # チェックポイント保存
            sim.metadata_json = {
                **dict(sim.metadata_json or {}),
                "pulse_result": {
                    "aggregation": pulse.aggregation,
                    "evaluation": pulse.evaluation,
                    "usage": pulse.usage,
                },
            }
            await session.commit()

            # === Phase 2: Council Deliberation ===
            await sse_manager.publish(simulation_id, "unified_phase_changed", {
                "phase": "council",
                "index": 2,
                "total": 3,
            })

            council = await run_council(session, sim, pulse, theme)

            sim.metadata_json = {
                **dict(sim.metadata_json or {}),
                "council_result": {
                    "participants": council.participants,
                    "devil_advocate_summary": council.devil_advocate_summary,
                    "usage": council.usage,
                },
            }
            await session.commit()

            # === Phase 3: Synthesis ===
            await sse_manager.publish(simulation_id, "unified_phase_changed", {
                "phase": "synthesis",
                "index": 3,
                "total": 3,
            })

            synthesis = await run_synthesis(session, sim, pulse, council, theme)

            # 最終結果保存
            sim.metadata_json = {
                **dict(sim.metadata_json or {}),
                "unified_result": {
                    "type": "unified",
                    "decision_brief": synthesis.decision_brief,
                    "agreement_score": synthesis.agreement_score,
                    "content": synthesis.content,
                    "sections": synthesis.sections,
                    "society_summary": {
                        "aggregation": pulse.aggregation,
                        "evaluation": pulse.evaluation,
                    },
                    "council": {
                        "participants": council.participants,
                        "rounds": council.rounds,
                        "synthesis": council.synthesis,
                        "devil_advocate_summary": council.devil_advocate_summary,
                    },
                },
            }
            sim.status = "completed"
            sim.completed_at = datetime.now(timezone.utc)
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_completed", {
                "simulation_id": simulation_id,
                "mode": "unified",
                "agreement_score": synthesis.agreement_score,
                "recommendation": synthesis.decision_brief.get("recommendation", ""),
            })

            logger.info("Unified simulation %s completed", simulation_id)

        except Exception as e:
            logger.error("Unified simulation %s failed: %s", simulation_id, e, exc_info=True)
            await session.rollback()
            sim.status = "failed"
            sim.error_message = f"{type(e).__name__}: {e}"[:500]
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })
