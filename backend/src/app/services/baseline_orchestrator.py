"""Baseline Orchestrator: 単一LLMベースライン分析

学術比較用。エージェントなしの単一LLMプロンプトでテーマを分析し、
unified モードと同じフォーマットで結果を保存する。
"""

import json
import logging
from datetime import datetime, timezone

from src.app.database import async_session
from src.app.llm.client import LLMClient
from src.app.models.simulation import Simulation
from src.app.services.scenario_pair_status import refresh_scenario_pair_status
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def run_baseline(simulation_id: str) -> None:
    """ベースラインモードを実行する。

    単一の LLM 呼び出しでテーマを分析。
    temperature=0 で決定論的に実行。
    """
    logger.info("Starting baseline simulation %s", simulation_id)

    async with async_session() as session:
        sim = await session.get(Simulation, simulation_id)
        if not sim:
            logger.error("Simulation %s not found", simulation_id)
            return

        theme = sim.prompt_text
        llm = LLMClient()

        try:
            await sse_manager.publish(simulation_id, "unified_phase_changed", {
                "phase": "baseline_analysis",
                "index": 1,
                "total": 1,
            })

            system_prompt = (
                "あなたは戦略アナリストです。以下のテーマについて包括的な分析を行い、"
                "JSON形式で結果を返してください。\n\n"
                "出力JSON:\n"
                "{\n"
                '  "recommendation": "Go | No-Go | 条件付きGo",\n'
                '  "decision_summary": "1-2文の結論",\n'
                '  "why_now": "なぜ今判断するのか",\n'
                '  "key_findings": ["発見1", "発見2", ...],\n'
                '  "risks": ["リスク1", "リスク2", ...],\n'
                '  "opportunities": ["機会1", "機会2", ...],\n'
                '  "confidence": 0.0-1.0,\n'
                '  "next_steps": ["ステップ1", "ステップ2", ...]\n'
                "}"
            )

            user_prompt = f"テーマ: {theme}\n\n上記テーマを多角的に分析してください。"

            result, usage = await llm.call(
                task_name="report_generate",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    result = {"analysis": result, "recommendation": "条件付きGo", "confidence": 0.5}

            if not isinstance(result, dict):
                result = {"analysis": str(result), "recommendation": "条件付きGo", "confidence": 0.5}

            decision_brief = {
                "recommendation": result.get("recommendation", "条件付きGo"),
                "decision_summary": result.get("decision_summary", ""),
                "why_now": result.get("why_now", ""),
                "agreement_score": result.get("confidence", 0.5),
                "key_reasons": [
                    {"reason": f, "evidence": "ベースライン分析", "confidence": result.get("confidence", 0.5)}
                    for f in result.get("key_findings", [])[:5]
                ],
                "risk_factors": [
                    {"condition": r, "impact": "要検証"}
                    for r in result.get("risks", [])[:5]
                ],
                "next_steps": result.get("next_steps", []),
            }

            sim.metadata_json = {
                "unified_result": {
                    "type": "baseline",
                    "decision_brief": decision_brief,
                    "agreement_score": result.get("confidence", 0.5),
                    "content": f"# ベースライン分析レポート\n\n{result.get('decision_summary', '')}",
                    "sections": {"decision_brief": decision_brief},
                    "usage": usage,
                },
            }
            sim.status = "completed"
            sim.completed_at = datetime.now(timezone.utc)
            await refresh_scenario_pair_status(session, sim.scenario_pair_id)
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_completed", {
                "simulation_id": simulation_id,
                "mode": "baseline",
            })

            logger.info("Baseline simulation %s completed", simulation_id)

        except Exception as e:
            logger.error("Baseline simulation %s failed: %s", simulation_id, e, exc_info=True)
            await session.rollback()
            sim.status = "failed"
            sim.error_message = f"{type(e).__name__}: {e}"[:500]
            await refresh_scenario_pair_status(session, sim.scenario_pair_id)
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })
        finally:
            await llm.close()
