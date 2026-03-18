import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.models.project import Project
from src.app.models.document import Document

router = APIRouter()


@router.post("")
async def create_project(
    name: str = "新規プロジェクト",
    description: str = "",
    session: AsyncSession = Depends(get_session),
):
    project = Project(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at.isoformat(),
    }


@router.get("/{project_id}")
async def get_project(project_id: str, session: AsyncSession = Depends(get_session)):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at.isoformat(),
    }


@router.post("/{project_id}/documents")
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    content = await file.read()
    text_content = ""
    content_type = file.content_type or "text/plain"

    if content_type in ("text/plain", "text/markdown") or (
        file.filename and file.filename.endswith((".txt", ".md"))
    ):
        text_content = content.decode("utf-8")
    elif content_type == "application/pdf" or (
        file.filename and file.filename.endswith(".pdf")
    ):
        from src.app.services.document_parser import parse_pdf

        text_content = parse_pdf(content)
    else:
        text_content = content.decode("utf-8", errors="replace")

    doc = Document(
        id=str(uuid.uuid4()),
        project_id=project_id,
        filename=file.filename or "unnamed",
        content_type=content_type,
        text_content=text_content,
        char_count=len(text_content),
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return {
        "id": doc.id,
        "filename": doc.filename,
        "content_type": doc.content_type,
        "char_count": doc.char_count,
    }


@router.get("/{project_id}/documents")
async def list_documents(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Document).where(Document.project_id == project_id)
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "content_type": d.content_type,
            "char_count": d.char_count,
        }
        for d in docs
    ]
