from fastapi import APIRouter
from starlette.responses import StreamingResponse

from src.app.sse.manager import sse_manager

router = APIRouter()


@router.get("/{run_id}/stream")
async def stream_events(run_id: str):
    return StreamingResponse(
        sse_manager.subscribe(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
