"""PM Board Orchestrator: 複数PMペルソナが並列分析し、チーフPMが統合する"""

import asyncio
import logging
from pathlib import Path

import yaml

from src.app.config import settings
from src.app.llm.client import LLMClient
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

PM_PERSONAS = ["strategy_pm", "discovery_pm", "execution_pm"]
CHIEF_PM = "chief_pm"


def _load_pm_template(persona_name: str) -> dict:
    """PM ペルソナの YAML テンプレートを読み込む。"""
    template_path = settings.templates_dir / "ja" / "pm_board" / f"{persona_name}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(f"PM template not found: {template_path}")
    with open(template_path) as f:
        return yaml.safe_load(f)


async def run_pm_board(
    simulation_id: str,
    prompt_text: str,
    document_text: str = "",
) -> dict:
    """PM Board モードを実行する。

    1. 3人のPMが並列で分析
    2. チーフPMが統合・矛盾検出
    3. 11セクション構造化出力を生成
    """
    logger.info(f"Starting PM Board for simulation {simulation_id}")
    llm = LLMClient()

    input_context = prompt_text
    if document_text:
        input_context = f"{document_text}\n\n---\n\n追加コンテキスト:\n{prompt_text}"

    try:
        # === Phase 1: 各PMが並列分析 ===
        await sse_manager.publish(simulation_id, "pm_board_started", {
            "simulation_id": simulation_id,
            "personas": PM_PERSONAS,
        })

        async def analyze_with_persona(persona_name: str) -> dict:
            template = _load_pm_template(persona_name)
            system_prompt = (
                f"あなたは{template['display_name']}です。\n"
                f"{template['persona']['thinking_style']}\n\n"
                f"{template['prompts']['analyze']}"
            )

            await sse_manager.publish(simulation_id, "pm_analyzing", {
                "persona": persona_name,
                "display_name": template["display_name"],
                "status": "started",
            })

            result, usage = await llm.call_with_retry(
                task_name=f"pm_board_{persona_name}",
                system_prompt=system_prompt,
                user_prompt=f"以下の入力を分析してください:\n\n{input_context}",
                response_format={"type": "json_object"},
            )

            await sse_manager.publish(simulation_id, "pm_analyzing", {
                "persona": persona_name,
                "display_name": template["display_name"],
                "status": "completed",
            })

            return {
                "persona": persona_name,
                "display_name": template["display_name"],
                "analysis": result if isinstance(result, dict) else {"raw": str(result)},
                "usage": usage,
            }

        pm_results = await asyncio.gather(
            *[analyze_with_persona(p) for p in PM_PERSONAS],
            return_exceptions=True,
        )

        successful_results = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for r in pm_results:
            if isinstance(r, Exception):
                logger.error(f"PM analysis failed: {r}", exc_info=r)
            else:
                successful_results.append(r)
                for key in total_usage:
                    total_usage[key] += r["usage"].get(key, 0)

        if not successful_results:
            raise ValueError("全てのPM分析が失敗しました")

        await sse_manager.publish(simulation_id, "pm_analyses_completed", {
            "successful": len(successful_results),
            "failed": len(pm_results) - len(successful_results),
        })

        # === Phase 2: チーフPMが統合 ===
        await sse_manager.publish(simulation_id, "pm_synthesizing", {
            "persona": CHIEF_PM,
            "status": "started",
        })

        chief_template = _load_pm_template(CHIEF_PM)
        analyses_summary = "\n\n".join(
            f"## {r['display_name']}の分析\n```json\n{_safe_json_str(r['analysis'])}\n```"
            for r in successful_results
        )

        chief_system_prompt = (
            f"あなたは{chief_template['display_name']}です。\n"
            f"{chief_template['persona']['thinking_style']}\n\n"
            f"{chief_template['prompts']['synthesize']}"
        )

        synthesis_result, synthesis_usage = await llm.call_with_retry(
            task_name="pm_board_chief_pm",
            system_prompt=chief_system_prompt,
            user_prompt=(
                f"入力コンテキスト:\n{input_context}\n\n"
                f"各PMの分析結果:\n{analyses_summary}"
            ),
            response_format={"type": "json_object"},
        )

        for key in total_usage:
            total_usage[key] += synthesis_usage.get(key, 0)

        await sse_manager.publish(simulation_id, "pm_synthesizing", {
            "persona": CHIEF_PM,
            "status": "completed",
        })

        # === Phase 3: 11セクション構造化出力を組み立て ===
        synthesis = synthesis_result if isinstance(synthesis_result, dict) else {}
        strategy = _get_analysis(successful_results, "strategy_pm")
        discovery = _get_analysis(successful_results, "discovery_pm")
        execution = _get_analysis(successful_results, "execution_pm")

        output = {
            "type": "pm_board",
            "sections": {
                "core_question": synthesis.get("synthesis", {}).get(
                    "core_question", strategy.get("core_question", "")
                ),
                "assumptions": strategy.get("assumptions", []),
                "uncertainties": discovery.get("uncertainties", []),
                "risks": discovery.get("risks", []),
                "winning_hypothesis": strategy.get("winning_hypothesis", {}),
                "customer_validation_plan": discovery.get("customer_validation_plan", {}),
                "market_view": execution.get("market_view", {}),
                "gtm_hypothesis": execution.get("gtm_hypothesis", {}),
                "mvp_scope": execution.get("mvp_scope", {}),
                "plan_30_60_90": execution.get("plan_30_60_90", {}),
                "top_5_actions": synthesis.get("top_5_actions", []),
            },
            "contradictions": synthesis.get("contradictions", []),
            "overall_confidence": synthesis.get("overall_confidence", 0),
            "key_decision_points": synthesis.get("key_decision_points", []),
            "pm_analyses": [
                {"persona": r["persona"], "display_name": r["display_name"], "analysis": r["analysis"]}
                for r in successful_results
            ],
            "synthesis": synthesis,
            "usage": total_usage,
        }

        await sse_manager.publish(simulation_id, "pm_board_completed", {
            "simulation_id": simulation_id,
            "section_count": len(output["sections"]),
            "overall_confidence": output["overall_confidence"],
        })

        logger.info(f"PM Board completed for simulation {simulation_id}")
        return output

    finally:
        await llm.close()


def _get_analysis(results: list[dict], persona_name: str) -> dict:
    """特定のペルソナの分析結果を取得する。"""
    for r in results:
        if r["persona"] == persona_name:
            return r["analysis"]
    return {}


def _safe_json_str(obj: dict) -> str:
    """JSON を安全な文字列に変換する。"""
    import json
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(obj)
