import logging
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
from fastapi.middleware.cors import CORSMiddleware

from src.app.config import settings
from src.app.database import init_db, async_session
from src.app.api.routes import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_templates()
    yield


async def seed_templates():
    from src.app.models.template import Template
    from sqlalchemy import select

    templates_dir = settings.templates_dir / "ja"
    if not templates_dir.exists():
        return

    async with async_session() as session:
        for yaml_file in templates_dir.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            name = data.get("name", yaml_file.stem)
            result = await session.execute(
                select(Template).where(Template.name == name)
            )
            if result.scalar_one_or_none():
                continue

            template = Template(
                name=name,
                display_name=data.get("display_name", name),
                description=data.get("description", ""),
                category=data.get("category", ""),
                prompts=data.get("prompts", {}),
            )
            session.add(template)

        await session.commit()


app = FastAPI(
    title="Agent AI - Realtime Graph Multi-Agent Simulation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
