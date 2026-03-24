import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.database import Base
from src.app.models import _import_all_models
from src.app.models.conversation_log import (
    CONVERSATION_LOG_ADDRESSED_TO_MAX_LENGTH,
    CONVERSATION_LOG_PARTICIPANT_NAME_MAX_LENGTH,
    CONVERSATION_LOG_PARTICIPANT_ROLE_MAX_LENGTH,
    CONVERSATION_LOG_PHASE_MAX_LENGTH,
    CONVERSATION_LOG_STANCE_MAX_LENGTH,
    ConversationLog,
)
from src.app.models.simulation import Simulation
from src.app.services.conversation_log_store import (
    normalize_conversation_log_entry,
    persist_conversation_logs,
)


def test_normalize_conversation_log_entry_clips_variable_length_fields():
    entry = ConversationLog(
        simulation_id=str(uuid.uuid4()),
        phase="m" * (CONVERSATION_LOG_PHASE_MAX_LENGTH + 10),
        round_number=1,
        participant_name="n" * (CONVERSATION_LOG_PARTICIPANT_NAME_MAX_LENGTH + 10),
        participant_role="r" * (CONVERSATION_LOG_PARTICIPANT_ROLE_MAX_LENGTH + 10),
        participant_index=0,
        content_text="content",
        content_json={},
        stance="s" * (CONVERSATION_LOG_STANCE_MAX_LENGTH + 10),
        addressed_to="a" * (CONVERSATION_LOG_ADDRESSED_TO_MAX_LENGTH + 10),
    )

    normalized = normalize_conversation_log_entry(entry)

    assert len(normalized.phase) == CONVERSATION_LOG_PHASE_MAX_LENGTH
    assert len(normalized.participant_name) == CONVERSATION_LOG_PARTICIPANT_NAME_MAX_LENGTH
    assert len(normalized.participant_role) == CONVERSATION_LOG_PARTICIPANT_ROLE_MAX_LENGTH
    assert len(normalized.stance) == CONVERSATION_LOG_STANCE_MAX_LENGTH
    assert len(normalized.addressed_to) == CONVERSATION_LOG_ADDRESSED_TO_MAX_LENGTH


@pytest.mark.asyncio
async def test_persist_conversation_logs_keeps_outer_session_usable(tmp_path):
    db_path = tmp_path / "conversation-log-store.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    _import_all_models()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        bad_entry = ConversationLog(
            simulation_id=None,  # type: ignore[arg-type]
            phase="meeting",
            round_number=1,
            participant_name="tester",
            participant_role="expert",
            participant_index=0,
            content_text="should fail",
            content_json={},
        )

        await persist_conversation_logs(session, [bad_entry], context="test logs")

        simulation = Simulation(
            id=str(uuid.uuid4()),
            mode="society",
            prompt_text="after failed log insert",
        )
        session.add(simulation)
        await session.commit()

        simulation_count = await session.scalar(select(func.count()).select_from(Simulation))
        log_count = await session.scalar(select(func.count()).select_from(ConversationLog))

        assert simulation_count == 1
        assert log_count == 0

    await engine.dispose()
