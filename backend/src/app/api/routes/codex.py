from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.services.codex_bridge import CodexAppServerClient
from src.app.services.codex_review_service import (
    CodexReviewMissingSimulation,
    CodexReviewNotReady,
    CodexReviewService,
    CodexReviewUnavailable,
)

router = APIRouter()

_bridge = CodexAppServerClient()


class CodexReviewRequest(BaseModel):
    question: str


def get_codex_review_service() -> CodexReviewService:
    return CodexReviewService(_bridge)


@router.get("/health")
async def get_codex_health():
    available = CodexAppServerClient.command_available()
    return {
        "enabled": settings.codex_enabled,
        "available": available,
        "initialized": _bridge.initialized,
        "transport": settings.codex_review_transport.strip().lower(),
        "mock": settings.codex_review_mock,
        "error": _bridge.last_error if settings.codex_enabled else "",
    }


async def create_codex_review(
    sim_id: str,
    body: CodexReviewRequest,
    session: AsyncSession,
    service: CodexReviewService,
):
    if not settings.codex_enabled:
        raise HTTPException(status_code=503, detail="Codex App Server未接続")
    if not settings.codex_transport_supported():
        raise HTTPException(status_code=503, detail="Codex review v1 supports only stdio transport")
    if not CodexAppServerClient.command_available():
        raise HTTPException(status_code=503, detail="Codex command is not available")
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="質問を入力してください")

    try:
        review = await service.review_simulation(session, sim_id, body.question)
    except CodexReviewMissingSimulation as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CodexReviewNotReady as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CodexReviewUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "id": review.id,
        "status": review.status,
        "answer": review.answer,
        "provider": "codex",
    }
