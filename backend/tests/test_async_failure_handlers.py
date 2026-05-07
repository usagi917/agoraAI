from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.models.simulation import Simulation


async def _create_simulation(db_session, **kwargs) -> Simulation:
    sim = Simulation(
        mode=kwargs.pop("mode", "standard"),
        prompt_text=kwargs.pop("prompt_text", "test prompt"),
        template_name=kwargs.pop("template_name", "g"),
        execution_profile=kwargs.pop("execution_profile", "preview"),
        scenario_pair_id=kwargs.pop("scenario_pair_id", "pair-without-row"),
        **kwargs,
    )
    db_session.add(sim)
    await db_session.commit()
    await db_session.refresh(sim)
    return sim


def _patch_session(module_path: str, db_session):
    patcher = patch(f"{module_path}.async_session")
    mock_session_ctx = patcher.start()
    mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
    mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
    return patcher


@pytest.mark.asyncio
async def test_unified_failure_handler_does_not_lazy_load_after_rollback(db_session):
    sim = await _create_simulation(db_session, mode="standard")
    session_patcher = _patch_session("src.app.services.unified_orchestrator", db_session)

    try:
        with patch(
            "src.app.services.unified_orchestrator.run_society_pulse",
            new_callable=AsyncMock,
            side_effect=RuntimeError("phase boom"),
        ):
            with patch("src.app.services.unified_orchestrator.sse_manager") as mock_sse:
                mock_sse.publish = AsyncMock()
                from src.app.services.unified_orchestrator import run_unified

                await run_unified(sim.id)
    finally:
        session_patcher.stop()

    updated = await db_session.get(Simulation, sim.id)
    assert updated.status == "failed"
    assert "phase boom" in updated.error_message


@pytest.mark.asyncio
async def test_baseline_failure_handler_does_not_lazy_load_after_rollback(db_session):
    sim = await _create_simulation(db_session, mode="baseline")
    session_patcher = _patch_session("src.app.services.baseline_orchestrator", db_session)

    llm = MagicMock()
    llm.call = AsyncMock(side_effect=RuntimeError("llm boom"))
    llm.close = AsyncMock()

    try:
        with patch("src.app.services.baseline_orchestrator.LLMClient", return_value=llm):
            with patch("src.app.services.baseline_orchestrator.sse_manager") as mock_sse:
                mock_sse.publish = AsyncMock()
                from src.app.services.baseline_orchestrator import run_baseline

                await run_baseline(sim.id)
    finally:
        session_patcher.stop()

    updated = await db_session.get(Simulation, sim.id)
    assert updated.status == "failed"
    assert "llm boom" in updated.error_message


@pytest.mark.asyncio
async def test_society_failure_handler_does_not_lazy_load_after_rollback(db_session):
    sim = await _create_simulation(db_session, mode="standard")
    session_patcher = _patch_session("src.app.services.society.society_orchestrator", db_session)

    try:
        with patch(
            "src.app.services.society.society_orchestrator._get_or_create_population",
            new_callable=AsyncMock,
            side_effect=RuntimeError("population boom"),
        ):
            with patch("src.app.services.society.society_orchestrator.sse_manager") as mock_sse:
                mock_sse.publish = AsyncMock()
                from src.app.services.society.society_orchestrator import run_society

                await run_society(sim.id)
    finally:
        session_patcher.stop()

    updated = await db_session.get(Simulation, sim.id)
    assert updated.status == "failed"
    assert "population boom" in updated.error_message
