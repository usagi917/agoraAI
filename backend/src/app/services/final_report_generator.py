"""最終統合レポートジェネレーター: 3段階パイプラインの結果を統合"""

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.llm.client import LLMClient
from src.app.models.report import Report
from src.app.models.simulation import Simulation
from src.app.services.pipeline_fallbacks import build_pipeline_report_fallback
from src.app.services.simulation_live_state import update_report_progress
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

FINAL_REPORT_SYSTEM_PROMPT = """\
あなたは統合分析レポートの専門家です。
3つの分析段階（因果推論、多視点検証、PM評価）の結果を受けて、
包括的かつ実用的な統合レポートを日本語で作成してください。

以下のセクション構造に従ってください:

# 統合分析レポート

## エグゼクティブサマリー
3段階の分析から得られた最も重要な発見と推奨事項の要約。

## 因果分析の知見（Stage 1）
Single Analysis から得られた因果関係、主要エンティティ、動態の要約。

## シナリオ検証結果（Stage 2）
Swarm Analysis から得られた主要シナリオ、確率分布、多様な視点からの検証結果。

## PM実務評価（Stage 3）
PM Board から得られた前提条件、リスク、勝利仮説、アクションプランの要約。

## 統合的知見
3段階を横断して見えてくるパターン、矛盾点、新たな洞察。

## リスクと不確実性
総合的なリスク評価と対策。

## 推奨アクション
優先度順のアクションリスト。

## 結論
最終的な判断と今後の検討事項。
"""


async def generate_final_report(
    session: AsyncSession,
    sim: Simulation,
    single_result: dict,
    swarm_result: dict,
    pm_result: dict,
) -> str:
    """3段階の結果を統合してレポートを生成し、Report テーブルに保存する。"""
    logger.info(f"Generating final report for simulation {sim.id}")
    llm = LLMClient()

    report_section_names = [
        "エグゼクティブサマリー",
        "因果分析の知見",
        "シナリオ検証結果",
        "PM実務評価",
        "統合的知見",
        "リスクと不確実性",
        "推奨アクション",
        "結論",
    ]

    try:
        await sse_manager.publish(sim.id, "report_started", {
            "sections": report_section_names,
        })
        await update_report_progress(
            session,
            simulation_id=sim.id,
            status="running",
            scope="pipeline",
            sections=report_section_names,
            completed_sections=[],
            last_error="",
        )

        # 入力コンテキストを構築
        context_parts = []

        # Single の結果
        report_content = single_result.get("report_content", "")
        if report_content:
            context_parts.append(f"## Stage 1: 因果分析結果\n\n{report_content}")

        # Swarm の結果
        integrated_report = swarm_result.get("integrated_report", "")
        if integrated_report:
            context_parts.append(f"## Stage 2: 多視点検証結果\n\n{integrated_report}")

        aggregation = swarm_result.get("aggregation", {})
        scenarios = aggregation.get("scenarios", [])
        if scenarios:
            scenario_summary = "\n".join(
                f"- {s.get('description', '?')}: {s.get('probability', 0):.0%}"
                for s in scenarios[:10]
            )
            context_parts.append(f"### シナリオ確率分布\n{scenario_summary}")

        # PM Board の結果
        if pm_result:
            sections = pm_result.get("sections", {})
            pm_summary_parts = []
            if sections.get("core_question"):
                pm_summary_parts.append(f"核心質問: {sections['core_question']}")
            if sections.get("winning_hypothesis"):
                wh = sections["winning_hypothesis"]
                pm_summary_parts.append(
                    f"勝利仮説: IF {wh.get('if_true', '')} "
                    f"THEN {wh.get('then_do', '')} "
                    f"TO ACHIEVE {wh.get('to_achieve', '')}"
                )
            if sections.get("top_5_actions"):
                actions = sections["top_5_actions"]
                action_list = "\n".join(
                    f"  {i+1}. {a.get('action', '')}" for i, a in enumerate(actions)
                )
                pm_summary_parts.append(f"トップ5アクション:\n{action_list}")

            contradictions = pm_result.get("contradictions", [])
            if contradictions:
                contra_list = "\n".join(
                    f"- {c.get('between', [])} : {c.get('issue', '')}" for c in contradictions
                )
                pm_summary_parts.append(f"矛盾点:\n{contra_list}")

            confidence = pm_result.get("overall_confidence", 0)
            pm_summary_parts.append(f"総合確信度: {confidence:.0%}")
            context_parts.append(f"## Stage 3: PM評価結果\n\n" + "\n\n".join(pm_summary_parts))

        user_prompt = (
            f"以下の3段階分析結果を統合して、包括的なレポートを作成してください。\n\n"
            f"元のプロンプト: {sim.prompt_text}\n\n"
            + "\n\n---\n\n".join(context_parts)
        )

        # トークン数制限のためにコンテキストをトリミング
        if len(user_prompt) > 30000:
            user_prompt = user_prompt[:30000] + "\n\n[...コンテキスト後半省略...]"

        result, usage = await llm.call_with_retry(
            task_name="final_report",
            system_prompt=FINAL_REPORT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        final_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        used_fallback = not final_content.strip()
        if used_fallback:
            logger.warning(
                "Final report LLM output was empty for simulation %s. Using fallback report builder.",
                sim.id,
            )
            final_content = build_pipeline_report_fallback(
                prompt_text=sim.prompt_text,
                single_report=single_result.get("report_content", ""),
                swarm_report=swarm_result.get("integrated_report", ""),
                scenarios=swarm_result.get("aggregation", {}).get("scenarios", []),
                pm_result=pm_result,
            )
        completed_sections: list[str] = []

        # セクション完了をSSEで通知
        for i, section_name in enumerate(report_section_names):
            if f"## {section_name}" in final_content or f"# {section_name}" in final_content:
                await sse_manager.publish(sim.id, "report_section_done", {
                    "section": section_name,
                    "index": i,
                })
                completed_sections.append(section_name)
                await update_report_progress(
                    session,
                    simulation_id=sim.id,
                    status="running",
                    completed_sections=completed_sections,
                )

        # Report テーブルに保存（run_id が必要なため、sim.run_id を使用）
        if sim.run_id:
            from sqlalchemy import select
            existing = await session.execute(
                select(Report).where(Report.run_id == sim.run_id)
            )
            report_record = existing.scalar_one_or_none()
            if report_record:
                # 既存レポートのコンテンツを統合レポートで更新
                report_record.content = final_content
                report_record.sections = {
                    "type": "pipeline_final",
                    "generated_with_fallback": used_fallback,
                    "single_report": single_result.get("report_content", "")[:2000],
                    "swarm_report": swarm_result.get("integrated_report", "")[:2000],
                    "pm_result": {
                        "core_question": pm_result.get("sections", {}).get("core_question", ""),
                        "overall_confidence": pm_result.get("overall_confidence", 0),
                    },
                }
                report_record.completed_at = datetime.now(timezone.utc)
            else:
                report_record = Report(
                    id=str(uuid.uuid4()),
                    run_id=sim.run_id,
                    content=final_content,
                    sections={
                        "type": "pipeline_final",
                        "generated_with_fallback": used_fallback,
                        "single_report": single_result.get("report_content", "")[:2000],
                        "swarm_report": swarm_result.get("integrated_report", "")[:2000],
                        "pm_result": {
                            "core_question": pm_result.get("sections", {}).get("core_question", ""),
                            "overall_confidence": pm_result.get("overall_confidence", 0),
                        },
                    },
                    status="completed",
                    completed_at=datetime.now(timezone.utc),
                )
                session.add(report_record)

        await session.commit()
        await update_report_progress(
            session,
            simulation_id=sim.id,
            status="completed",
            completed_sections=completed_sections,
            last_error="",
        )

        await sse_manager.publish(sim.id, "report_completed", {
            "report_length": len(final_content),
            "type": "pipeline_final",
        })

        logger.info(f"Final report generated for simulation {sim.id}: {len(final_content)} chars")
        return final_content
    except Exception as exc:
        await update_report_progress(
            session,
            simulation_id=sim.id,
            status="failed",
            last_error=str(exc)[:200],
        )
        raise

    finally:
        await llm.close()
