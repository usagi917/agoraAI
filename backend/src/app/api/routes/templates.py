from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.models.template import Template

router = APIRouter()


@router.get("")
async def list_templates(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Template))
    templates = result.scalars().all()
    payload = [
        {
            "id": t.id,
            "name": t.name,
            "display_name": t.display_name,
            "description": t.description,
            "category": t.category,
        }
        for t in templates
    ]
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "public, max-age=300"},
    )
