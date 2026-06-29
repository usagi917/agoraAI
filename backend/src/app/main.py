import logging
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import cast

import yaml
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from src.app.api.routes import api_router
from src.app.config import settings
from src.app.database import async_session, init_db
from src.app.llm.client import validate_task_registry
from src.app.services.simulation_dispatcher import (
    release_startup_resume_leadership,
    resume_unfinished_simulations,
)


def _text_value(value: object, default: str) -> str:
    return value if isinstance(value, str) else default


def _mapping_value(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}

    mapping = cast(Mapping[object, object], value)
    return {str(key): item for key, item in mapping.items()}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    validate_task_registry()
    await init_db()
    await seed_templates()
    _ = await resume_unfinished_simulations()
    try:
        yield
    finally:
        await release_startup_resume_leadership()


async def seed_templates() -> None:
    from sqlalchemy import select

    from src.app.models.template import Template

    templates_dir = settings.templates_dir / "ja"
    if not templates_dir.exists():
        return

    async with async_session() as session:
        for yaml_file in templates_dir.glob("*.yaml"):
            with open(yaml_file) as f:
                loaded = cast(object, yaml.safe_load(f))

            if not isinstance(loaded, Mapping):
                continue

            data = cast(Mapping[str, object], loaded)

            name = _text_value(data.get("name"), yaml_file.stem)
            result = await session.execute(
                select(Template).where(Template.name == name)
            )
            if result.scalar_one_or_none():
                continue

            template = Template(
                name=name,
                display_name=_text_value(data.get("display_name"), name),
                description=_text_value(data.get("description"), ""),
                category=_text_value(data.get("category"), ""),
                prompts=_mapping_value(data.get("prompts")),
            )
            session.add(template)

        await session.commit()


app = FastAPI(
    title="Agent AI - Realtime Graph Multi-Agent Simulation",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "llm_provider": settings.llm_provider(),
        "live_simulation_available": settings.live_simulation_available(),
        "live_simulation_message": settings.live_simulation_message(),
    }
