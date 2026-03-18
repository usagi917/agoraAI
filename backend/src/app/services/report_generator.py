"""レポート生成: セクション単位で LLM 呼び出し"""

import json
import logging
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.llm.client import llm_client
from src.app.llm.prompts import (
    REPORT_SECTION_SYSTEM,
    REPORT_SECTION_USER,
    REPORT_SECTIONS,
)
from src.app.models.report import Report
from src.app.services.cost_tracker import record_usage
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def generate_report(
    session: AsyncSession,
    run_id: str,
    world_state_final: dict,
    events: list[dict],
    agents: dict,
    template_sections: list[str] | None = None,
) -> str:
    """セクション毎にレポートを生成する。"""

    await sse_manager.publish(run_id, "report_started", {"message": "レポート生成を開始します"})

    sections_to_generate = template_sections or list(REPORT_SECTIONS.keys())
    report_content = "# シミュレーション分析レポート\n\n"
    sections_data = {}

    for section_key in sections_to_generate:
        section_display = REPORT_SECTIONS.get(section_key, section_key)

        # プロンプトサイズ縮小（ローカルLLM対応）
        compact_state = {
            "entities": [{"label": e.get("label"), "type": e.get("entity_type")} for e in world_state_final.get("entities", [])],
            "summary": world_state_final.get("world_summary", ""),
        }
        compact_events = [{"title": ev.get("title"), "type": ev.get("event_type")} for ev in events[:10]]
        compact_agents = [{"name": a.get("name"), "role": a.get("role")} for a in agents.get("agents", [])]

        user_prompt = REPORT_SECTION_USER.format(
            section_name=section_key,
            section_display_name=section_display,
            world_state_final=json.dumps(compact_state, ensure_ascii=False)[:2000],
            events=json.dumps(compact_events, ensure_ascii=False)[:1500],
            agents=json.dumps(compact_agents, ensure_ascii=False)[:1000],
        )

        result, usage = await llm_client.call(
            task_name="report_generate",
            system_prompt=REPORT_SECTION_SYSTEM,
            user_prompt=user_prompt,
        )

        await record_usage(session, run_id, f"report_{section_key}", usage)

        section_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        report_content += f"## {section_display}\n\n{section_content}\n\n---\n\n"
        sections_data[section_key] = section_content

        await sse_manager.publish(run_id, "report_section_done", {
            "section": section_key,
            "display_name": section_display,
            "content": section_content,
        })

    # レポート保存
    report = Report(
        id=str(uuid.uuid4()),
        run_id=run_id,
        content=report_content,
        sections=sections_data,
        status="completed",
        completed_at=datetime.utcnow(),
    )
    session.add(report)
    await session.flush()

    logger.info(f"Report generated for run {run_id}: {len(sections_data)} sections")
    return report_content
