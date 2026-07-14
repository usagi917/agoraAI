"""Durable per-agent activation checkpoint tests."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.app.database import Base
from src.app.models.agent_activation_result import AgentActivationResult
from src.app.services.society.activation_store import (
    activation_stage_counts,
    load_completed_response_rows,
    load_completed_responses,
    load_preferred_response_rows,
    persist_activation_chunk,
)


@pytest.mark.asyncio
async def test_activation_store_upserts_and_only_resumes_successes() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        await persist_activation_chunk(
            session,
            simulation_id="sim-1",
            population_id="pop-1",
            stage="local_initial",
            run_seed=7,
            records=[
                {
                    "agent_id": "a-1",
                    "agent_index": 1,
                    "provider": "liquid",
                    "model": "lfm",
                    "response": {"stance": "賛成", "confidence": 0.6},
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
                {
                    "agent_id": "a-2",
                    "agent_index": 2,
                    "provider": "liquid",
                    "model": "lfm",
                    "response": {"_failed": True, "stance": "", "confidence": 0},
                    "usage": {"total_tokens": 0},
                },
                {
                    "agent_id": "a-3",
                    "agent_index": 3,
                    "provider": "liquid",
                    "model": "lfm",
                    "response": {"stance": "反対", "confidence": 0.7},
                    "usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
                },
            ],
        )
        await persist_activation_chunk(
            session,
            simulation_id="sim-1",
            population_id="pop-1",
            stage="social_final",
            run_seed=7,
            records=[
                {
                    "agent_id": "a-1",
                    "agent_index": 1,
                    "provider": "social_dynamics",
                    "response": {
                        "stance": "中立",
                        "confidence": 0.7,
                        "initial_stance": "条件付き賛成",
                    },
                    "usage": {},
                }
            ],
        )
        await persist_activation_chunk(
            session,
            simulation_id="sim-1",
            population_id="pop-1",
            stage="local_initial",
            run_seed=7,
            records=[
                {
                    "agent_id": "a-1",
                    "agent_index": 1,
                    "provider": "liquid",
                    "model": "lfm",
                    "response": {"stance": "条件付き賛成", "confidence": 0.8},
                    "usage": {"prompt_tokens": 11, "completion_tokens": 6, "total_tokens": 17},
                }
            ],
        )

        completed = await load_completed_responses(
            session,
            simulation_id="sim-1",
            stage="local_initial",
            run_seed=7,
            provider="liquid",
        )
        counts = await activation_stage_counts(session, "sim-1")
        ordered_rows = await load_completed_response_rows(
            session,
            simulation_id="sim-1",
            stage="local_initial",
        )
        preferred_rows = await load_preferred_response_rows(
            session,
            simulation_id="sim-1",
        )
        rows = list((await session.scalars(select(AgentActivationResult))).all())

    await engine.dispose()

    assert len(rows) == 4
    assert completed == {
        "a-1": {"stance": "条件付き賛成", "confidence": 0.8},
        "a-3": {"stance": "反対", "confidence": 0.7},
    }
    assert [(row.agent_id, row.agent_index) for row in ordered_rows] == [
        ("a-1", 1),
        ("a-3", 3),
    ]
    assert [(row.agent_id, row.stage, row.stance) for row in preferred_rows] == [
        ("a-1", "social_final", "中立"),
        ("a-3", "local_initial", "反対"),
    ]
    assert counts == {
        "local_initial": {"success": 2, "failed": 1},
        "social_final": {"success": 1},
    }


@pytest.mark.asyncio
async def test_activation_runs_in_chunks_and_preserves_resume_order() -> None:
    from src.app.services.society.activation_layer import run_activation

    agents = [
        {
            "id": f"a-{index}",
            "agent_index": index,
            "demographics": {"age": 30 + index, "occupation": "会社員", "region": "関東"},
            "big_five": {},
            "values": {},
        }
        for index in range(5)
    ]
    resume = {"a-0": {"stance": "中立", "confidence": 0.5, "reason": "resume"}}
    batch_calls: list[list[dict]] = []
    checkpoint_records: list[list[dict]] = []

    async def fake_batch(calls: list[dict], max_concurrency: int):
        batch_calls.append(calls)
        return [
            (
                {
                    "stance": "賛成",
                    "confidence": 0.7,
                    "reason": "理由",
                    "concern": "懸念",
                    "priority": "優先",
                },
                {
                    "provider": "liquid",
                    "model": "lfm",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            )
            for _ in calls
        ]

    async def on_chunk(records: list[dict], completed: int, total: int) -> None:
        checkpoint_records.append(records)
        assert completed <= total == 5

    with (
        patch("src.app.services.society.activation_layer.multi_llm_client.initialize"),
        patch(
            "src.app.services.society.activation_layer.multi_llm_client.call_batch_by_provider",
            new=AsyncMock(side_effect=fake_batch),
        ),
    ):
        result = await run_activation(
            agents,
            "テーマ",
            provider_override="liquid",
            compact=True,
            chunk_size=2,
            max_concurrency=2,
            resume_responses=resume,
            on_chunk=on_chunk,
        )

    assert [len(calls) for calls in batch_calls] == [1, 2, 1]
    assert sum(len(records) for records in checkpoint_records) == 4
    assert result["responses"][0]["reason"] == "resume"
    assert [response["agent_id"] for response in result["responses"]] == [
        "a-0",
        "a-1",
        "a-2",
        "a-3",
        "a-4",
    ]
    assert result["usage"]["by_provider"]["liquid"]["calls"] == 4
    assert all(
        call["response_format"]["type"] == "json_schema" for calls in batch_calls for call in calls
    )


@pytest.mark.asyncio
async def test_activation_aborts_after_a_fully_failed_local_chunk() -> None:
    from src.app.services.society.activation_layer import (
        ActivationStageUnavailableError,
        run_activation,
    )

    agents = [
        {"id": f"a-{index}", "agent_index": index, "demographics": {}, "big_five": {}}
        for index in range(5)
    ]

    async def failed_batch(calls: list[dict], _max_concurrency: int):
        return [
            (
                {"_error": True, "_error_msg": "Ollama unavailable"},
                {"provider": "liquid", "_failed": True},
            )
            for _ in calls
        ]

    batch = AsyncMock(side_effect=failed_batch)
    with (
        patch("src.app.services.society.activation_layer.multi_llm_client.initialize"),
        patch(
            "src.app.services.society.activation_layer.multi_llm_client.call_batch_by_provider",
            new=batch,
        ),
    ):
        with pytest.raises(ActivationStageUnavailableError, match="liquid"):
            await run_activation(
                agents,
                "テーマ",
                provider_override="liquid",
                compact=True,
                chunk_size=2,
                abort_on_full_chunk_failure=True,
            )

    assert batch.await_count == 1


@pytest.mark.asyncio
async def test_fully_resumed_stage_does_not_require_running_ollama() -> None:
    from src.app.services.society.activation_layer import run_activation

    agents = [
        {"id": "a-1", "agent_index": 1, "demographics": {}, "big_five": {}},
        {"id": "a-2", "agent_index": 2, "demographics": {}, "big_five": {}},
    ]
    resumed = {
        agent["id"]: {"stance": "中立", "confidence": 0.5}
        for agent in agents
    }

    with (
        patch("src.app.services.society.activation_layer.multi_llm_client.initialize"),
        patch(
            "src.app.services.society.activation_layer.multi_llm_client.ensure_provider_ready",
            new=AsyncMock(),
        ) as ready,
        patch(
            "src.app.services.society.activation_layer.multi_llm_client.call_batch_by_provider",
            new=AsyncMock(),
        ) as batch,
    ):
        result = await run_activation(
            agents,
            "テーマ",
            provider_override="liquid",
            compact=True,
            resume_responses=resumed,
            require_provider_ready=True,
        )

    ready.assert_not_awaited()
    batch.assert_not_awaited()
    assert len(result["responses"]) == 2
