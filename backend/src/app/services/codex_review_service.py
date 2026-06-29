import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.database import utcnow_naive
from src.app.models.codex_review import CodexReview
from src.app.models.report import Report
from src.app.models.simulation import Simulation
from src.app.models.world_state import WorldState
from src.app.services.codex_bridge import CodexAppServerClient, CodexBridgeError
from src.app.services.decision_briefing import build_single_decision_brief

CODEX_CONTEXT_CHAR_LIMIT = 24000
CODEX_FIELD_CHAR_LIMIT = 900
CODEX_LIST_ITEM_LIMIT = 3
CODEX_DICT_KEY_LIMIT = 8


class CodexReviewUnavailable(RuntimeError):
    pass


class CodexReviewMissingSimulation(RuntimeError):
    pass


class CodexReviewNotReady(RuntimeError):
    pass


class CodexReviewService:
    def __init__(self, bridge: CodexAppServerClient | None = None) -> None:
        self.bridge = bridge or CodexAppServerClient()

    async def review_simulation(
        self,
        session: AsyncSession,
        simulation_id: str,
        question: str,
    ) -> CodexReview:
        sim = await session.get(Simulation, simulation_id)
        if not sim:
            raise CodexReviewMissingSimulation("Simulation が見つかりません")

        review = CodexReview(
            id=str(uuid.uuid4()),
            simulation_id=sim.id,
            run_id=sim.run_id,
            question=question,
            status="pending",
        )
        session.add(review)
        await session.commit()

        try:
            prompt = await self._build_prompt(session, sim, question)
            answer = await self.bridge.run_turn(prompt)
            review.answer = answer
            review.status = "completed"
            review.completed_at = utcnow_naive()
            await session.commit()
            await session.refresh(review)
            return review
        except CodexReviewNotReady:
            review.status = "failed"
            review.error_message = "report_not_generated"
            review.completed_at = utcnow_naive()
            await session.commit()
            raise
        except CodexBridgeError as exc:
            review.status = "failed"
            review.error_message = str(exc)
            review.completed_at = utcnow_naive()
            await session.commit()
            raise CodexReviewUnavailable(str(exc)) from exc
        except Exception as exc:
            review.status = "failed"
            review.error_message = str(exc)
            review.completed_at = utcnow_naive()
            await session.commit()
            raise

    async def _build_prompt(self, session: AsyncSession, sim: Simulation, question: str) -> str:
        report_payload = await self._load_report_payload(session, sim)
        if not report_payload:
            raise CodexReviewNotReady("レポートがまだ生成されていません")

        world_state = await self._load_latest_world_state(session, sim.run_id)
        decision_brief = self._build_decision_brief(sim, report_payload)
        context = {
            "simulation": {
                "id": sim.id,
                "mode": sim.mode,
                "prompt_text": sim.prompt_text,
                "template_name": sim.template_name,
                "execution_profile": sim.execution_profile,
                "status": sim.status,
            },
            "decision_brief": self._compact_for_codex(decision_brief),
            "report": self._compact_for_codex(report_payload),
            "latest_world_state": self._compact_for_codex(world_state, max_chars=6000),
        }
        context_json = json.dumps(context, ensure_ascii=False, indent=2, default=str)
        context_char_limit = settings.codex_review_max_context_chars
        if len(context_json) > context_char_limit:
            context_json = (
                context_json[:context_char_limit]
                + "\n...TRUNCATED: Codex review context was shortened for latency..."
            )
        return CODEX_REVIEW_PROMPT.format(
            question=question.strip(),
            context=context_json,
        )

    async def _load_report_payload(self, session: AsyncSession, sim: Simulation) -> dict:
        metadata = dict(sim.metadata_json or {})
        for key in ("unified_result", "society_first_result", "meta_simulation_result"):
            payload = metadata.get(key)
            if isinstance(payload, dict) and payload:
                return payload

        if metadata.get("pm_analyses"):
            return metadata

        if sim.run_id:
            result = await session.execute(select(Report).where(Report.run_id == sim.run_id))
            report = result.scalar_one_or_none()
            if report and report.status == "completed":
                return {
                    "type": "single",
                    "id": report.id,
                    "run_id": report.run_id,
                    "content": report.content,
                    "sections": report.sections,
                    "status": report.status,
                }
        return {}

    async def _load_latest_world_state(self, session: AsyncSession, run_id: str | None) -> dict:
        if not run_id:
            return {}
        result = await session.execute(
            select(WorldState)
            .where(WorldState.run_id == run_id)
            .order_by(WorldState.round_number.desc())
            .limit(1)
        )
        state = result.scalar_one_or_none()
        if not state:
            return {}
        return {
            "round_number": state.round_number,
            "state_data": state.state_data,
            "created_at": state.created_at.isoformat() if state.created_at else None,
        }

    def _build_decision_brief(self, sim: Simulation, report_payload: dict) -> dict:
        if isinstance(report_payload.get("decision_brief"), dict):
            return report_payload["decision_brief"]
        sections = report_payload.get("sections")
        if isinstance(sections, dict) and isinstance(sections.get("decision_brief"), dict):
            return sections["decision_brief"]
        return build_single_decision_brief(
            prompt_text=sim.prompt_text,
            report_content=str(report_payload.get("content") or report_payload.get("summary_markdown") or ""),
            sections=dict(sections or {}),
            quality=dict(report_payload.get("quality") or {}),
        )

    def _compact_for_codex(self, value, *, max_chars: int = CODEX_FIELD_CHAR_LIMIT, depth: int = 0):
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return self._trim_text(value, max_chars)
        if depth >= 4:
            return self._trim_text(json.dumps(value, ensure_ascii=False, default=str), max_chars)
        if isinstance(value, list):
            items = [
                self._compact_for_codex(item, max_chars=max_chars, depth=depth + 1)
                for item in value[:CODEX_LIST_ITEM_LIMIT]
            ]
            if len(value) > CODEX_LIST_ITEM_LIMIT:
                items.append({"_truncated_items": len(value) - CODEX_LIST_ITEM_LIMIT})
            return items
        if isinstance(value, dict):
            compacted = {}
            keys = self._ordered_context_keys(value)
            for key in keys[:CODEX_DICT_KEY_LIMIT]:
                compacted[key] = self._compact_for_codex(
                    value[key],
                    max_chars=max_chars,
                    depth=depth + 1,
                )
            if len(keys) > CODEX_DICT_KEY_LIMIT:
                compacted["_truncated_keys"] = len(keys) - CODEX_DICT_KEY_LIMIT
            return compacted
        return self._trim_text(str(value), max_chars)

    @staticmethod
    def _ordered_context_keys(value: dict) -> list:
        priority = [
            "decision_brief",
            "recommendation",
            "summary",
            "summary_markdown",
            "executive_summary",
            "quality",
            "evidence",
            "key_findings",
            "rationale",
            "critical_unknowns",
            "next_steps",
            "recommended_actions",
            "scenario_comparison",
            "council_summary",
            "social_pulse",
            "stance_distribution",
            "participants",
            "conversation_highlights",
            "risks",
            "transcript",
        ]
        ordered = [key for key in priority if key in value]
        ordered.extend(key for key in value.keys() if key not in ordered)
        return ordered

    @staticmethod
    def _trim_text(value: str, max_chars: int) -> str:
        if len(value) <= max_chars:
            return value
        return value[:max_chars] + f"...TRUNCATED {len(value) - max_chars} chars..."


CODEX_REVIEW_PROMPT = """あなたは AgoraAI の Codex Review Agent です。
完了済みシミュレーションのレポートだけをレビューし、質問に日本語で回答してください。

制約:
- コマンド実行、ファイル変更、外部通信、追加ツール利用は依頼しない。
- 与えられたコンテキストに基づく根拠と推論を分ける。
- 不明な点は不明と明示する。
- 意思決定者が次に何を検証すべきかを具体化する。

回答フォーマット:
1. 結論
2. 根拠
3. 弱い前提
4. 反証・別解
5. 意思決定リスク
6. 次に検証すべきこと

質問:
{question}

コンテキスト:
{context}
"""
