"""Swarm 統合レポート生成

MiroFish の ReACT パターンに倣い、複数コロニーの分析結果を
多段階推論で統合し、単一視点では得られない深い洞察を生成する。
"""

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.llm.client import llm_client
from src.app.llm.prompts import SWARM_REPORT_SYSTEM, SWARM_REPORT_USER
from src.app.services.cost_tracker import record_usage
from src.app.services.simulation_live_state import update_report_progress
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)
FORCE_REPORT_FAILURE_TOKEN = "[[FAIL_REPORT]]"


def _summarize_colony(colony_result: dict, config) -> str:
    """1つのコロニー結果を要約テキストに変換する。"""
    events = colony_result.get("events", [])
    world_state = colony_result.get("world_state", {})
    agents = colony_result.get("agents", {})

    event_summaries = []
    for ev in events[:8]:
        title = ev.get("title", "")
        desc = ev.get("description", "")[:150]
        event_summaries.append(f"- {title}: {desc}")

    entity_summaries = []
    for e in world_state.get("entities", [])[:6]:
        label = e.get("label", "")
        stance = e.get("stance", "")
        importance = e.get("importance_score", 0)
        entity_summaries.append(f"- {label} (重要度:{importance:.1f}, 立場:{stance})")

    agent_summaries = []
    for a in agents.get("agents", [])[:5]:
        name = a.get("name", "")
        role = a.get("role", "")
        goals = ", ".join(a.get("goals", [])[:2])
        agent_summaries.append(f"- {name} ({role}): {goals}")

    return f"""### コロニー: {config.perspective_label}
- 温度: {config.temperature}
- 対立的視点: {"はい" if config.adversarial else "いいえ"}

**主要イベント:**
{chr(10).join(event_summaries) or "なし"}

**エンティティ状態:**
{chr(10).join(entity_summaries) or "なし"}

**エージェント行動:**
{chr(10).join(agent_summaries) or "なし"}

**世界サマリー:** {world_state.get("world_summary", "")[:300]}
"""


async def generate_swarm_integrated_report(
    session: AsyncSession,
    simulation_id: str,
    prompt_text: str,
    colony_results: list[dict],
    colony_configs: list,
    aggregation: dict,
) -> str:
    """複数コロニーの結果を統合した深い分析レポートを生成する。"""

    # コロニーサマリーの構築
    colony_summaries = []
    config_map = {c.colony_id: c for c in colony_configs}
    for result in colony_results:
        colony_id = result.get("colony_id", "")
        config = config_map.get(colony_id)
        if config:
            colony_summaries.append(_summarize_colony(result, config))

    # シナリオのフォーマット
    scenarios = aggregation.get("scenarios", [])
    scenario_texts = []
    for i, s in enumerate(scenarios[:7], 1):
        prob = s.get("probability", 0)
        desc = s.get("description", "")
        agreement = s.get("agreement_ratio", 0)
        colonies = s.get("supporting_colonies", 0)
        total = s.get("total_colonies", 0)
        ci = s.get("ci", [0, 1])
        scenario_texts.append(
            f"{i}. [{prob*100:.1f}%] {desc}\n"
            f"   合意率: {agreement*100:.0f}% ({colonies}/{total}コロニー), "
            f"CI: [{ci[0]*100:.1f}%-{ci[1]*100:.1f}%]"
        )

    # 合意マトリクス要約
    matrix = aggregation.get("agreement_matrix", {})
    colony_ids = matrix.get("colony_ids", [])
    matrix_data = matrix.get("matrix", [])
    agreement_pairs = []
    for i in range(len(colony_ids)):
        for j in range(i + 1, len(colony_ids)):
            if matrix_data and i < len(matrix_data) and j < len(matrix_data[i]):
                val = matrix_data[i][j]
                if val > 0:
                    # コロニーラベルを取得
                    label_i = next(
                        (c.perspective_label for c in colony_configs if c.colony_id == colony_ids[i]),
                        colony_ids[i][:8],
                    )
                    label_j = next(
                        (c.perspective_label for c in colony_configs if c.colony_id == colony_ids[j]),
                        colony_ids[j][:8],
                    )
                    agreement_pairs.append(f"{label_i} ↔ {label_j}: {val*100:.0f}%")

    agreement_summary = "\n".join(agreement_pairs) if agreement_pairs else "コロニー間の合意は低い（各コロニーが独立した結論を導出）"

    # プロンプト構築
    user_prompt = SWARM_REPORT_USER.format(
        prompt_text=prompt_text[:1000],
        colony_summaries="\n\n".join(colony_summaries)[:6000],
        scenarios="\n".join(scenario_texts)[:3000],
        diversity_score=f"{aggregation.get('diversity_score', 0):.3f}",
        entropy=f"{aggregation.get('entropy', 0):.3f}",
        agreement_summary=agreement_summary[:1000],
    )

    section_name = "統合レポート"
    await sse_manager.publish(simulation_id, "report_started", {
        "message": "統合レポート生成を開始します",
        "colony_count": len(colony_results),
        "scenario_count": len(scenarios),
        "sections": [section_name],
    })
    await update_report_progress(
        session,
        simulation_id=simulation_id,
        status="running",
        scope="swarm",
        sections=[section_name],
        completed_sections=[],
        last_error="",
    )

    try:
        if FORCE_REPORT_FAILURE_TOKEN in prompt_text:
            raise RuntimeError("Forced report failure via [[FAIL_REPORT]] marker")

        result, usage = await llm_client.call(
            task_name="report_generate",
            system_prompt=SWARM_REPORT_SYSTEM,
            user_prompt=user_prompt,
        )
        await record_usage(session, simulation_id, "swarm_integrated_report", usage)

        report_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        await sse_manager.publish(simulation_id, "report_section_done", {
            "section": section_name,
            "display_name": section_name,
            "key": "integrated_report",
            "content": report_text,
        })
        await update_report_progress(
            session,
            simulation_id=simulation_id,
            status="running",
            completed_sections=[section_name],
        )

        return report_text
    except Exception as exc:
        await update_report_progress(
            session,
            simulation_id=simulation_id,
            status="failed",
            last_error=str(exc)[:200],
        )
        raise
