"""Simulation Dispatcher v2 テスト"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from src.app.models.simulation import Simulation


async def _create_simulation(db_session, **kwargs):
    sim = Simulation(
        mode=kwargs.pop("mode", "standard"),
        prompt_text=kwargs.pop("prompt_text", "test"),
        template_name=kwargs.pop("template_name", "g"),
        execution_profile=kwargs.pop("execution_profile", "preview"),
        **kwargs,
    )
    db_session.add(sim)
    await db_session.commit()
    await db_session.refresh(sim)
    return sim


class TestDispatchSimulation:
    @pytest.mark.asyncio
    async def test_dispatch_standard_calls_run_unified(self, db_session):
        sim = await _create_simulation(
            db_session,
            mode="standard", prompt_text="test prompt",
            template_name="g", execution_profile="preview",
        )

        with patch("src.app.services.simulation_dispatcher.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.app.services.simulation_dispatcher.run_unified", new_callable=AsyncMock) as mock_unified:
                with patch("src.app.services.simulation_dispatcher.run_baseline", new_callable=AsyncMock) as mock_baseline:
                    from src.app.services.simulation_dispatcher import dispatch_simulation
                    await dispatch_simulation(sim.id)

                    mock_unified.assert_called_once_with(sim.id)
                    mock_baseline.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_baseline_calls_run_baseline(self, db_session):
        sim = await _create_simulation(
            db_session,
            mode="baseline", prompt_text="test",
            template_name="g", execution_profile="preview",
        )

        with patch("src.app.services.simulation_dispatcher.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.app.services.simulation_dispatcher.run_unified", new_callable=AsyncMock) as mock_unified:
                with patch("src.app.services.simulation_dispatcher.run_baseline", new_callable=AsyncMock) as mock_baseline:
                    from src.app.services.simulation_dispatcher import dispatch_simulation
                    await dispatch_simulation(sim.id)

                    mock_baseline.assert_called_once_with(sim.id)
                    mock_unified.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_old_mode_normalizes(self, db_session):
        """旧モード名 'pipeline' が 'deep' に正規化されて unified が呼ばれる。"""
        sim = await _create_simulation(
            db_session,
            mode="pipeline", prompt_text="test",
            template_name="g", execution_profile="preview",
        )

        with patch("src.app.services.simulation_dispatcher.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.app.services.simulation_dispatcher.run_unified", new_callable=AsyncMock) as mock_unified:
                with patch("src.app.services.simulation_dispatcher.run_baseline", new_callable=AsyncMock):
                    from src.app.services.simulation_dispatcher import dispatch_simulation
                    await dispatch_simulation(sim.id)

                    mock_unified.assert_called_once()

        # DB上のmodeが正規化されていることを確認
        updated = await db_session.get(Simulation, sim.id)
        assert updated.mode == "deep"

    @pytest.mark.asyncio
    async def test_dispatch_missing_sim_returns_early(self, db_session):
        with patch("src.app.services.simulation_dispatcher.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.app.services.simulation_dispatcher.run_unified", new_callable=AsyncMock) as mock_unified:
                from src.app.services.simulation_dispatcher import dispatch_simulation
                await dispatch_simulation("nonexistent-id")

                mock_unified.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_error_sets_failed(self, db_session):
        sim = await _create_simulation(
            db_session,
            mode="standard", prompt_text="test",
            template_name="g", execution_profile="preview",
        )

        with patch("src.app.services.simulation_dispatcher.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.app.services.simulation_dispatcher.run_unified", new_callable=AsyncMock, side_effect=RuntimeError("LLM error")):
                with patch("src.app.services.simulation_dispatcher.sse_manager") as mock_sse:
                    mock_sse.publish = AsyncMock()
                    from src.app.services.simulation_dispatcher import dispatch_simulation
                    await dispatch_simulation(sim.id)

        updated = await db_session.get(Simulation, sim.id)
        assert updated.status == "failed"
        assert "LLM error" in updated.error_message


class TestResumeUnfinishedSimulations:
    @pytest.mark.asyncio
    async def test_skips_resume_when_not_startup_leader(self):
        from src.app.services.simulation_dispatcher import resume_unfinished_simulations

        with patch(
            "src.app.services.simulation_dispatcher._try_acquire_startup_resume_leadership",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch("src.app.services.simulation_dispatcher.spawn_simulation") as mock_spawn:
                resumed_count = await resume_unfinished_simulations()

        assert resumed_count == 0
        mock_spawn.assert_not_called()

    @pytest.mark.asyncio
    async def test_startup_leader_spawns_only_unfinished_simulations(self, db_session):
        queued = await _create_simulation(db_session, status="queued")
        running = await _create_simulation(db_session, status="running")
        await _create_simulation(db_session, status="completed")

        with patch(
            "src.app.services.simulation_dispatcher._try_acquire_startup_resume_leadership",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch("src.app.services.simulation_dispatcher.async_session") as mock_session_ctx:
                mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
                mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                with patch("src.app.services.simulation_dispatcher.spawn_simulation") as mock_spawn:
                    from src.app.services.simulation_dispatcher import resume_unfinished_simulations

                    resumed_count = await resume_unfinished_simulations()

        assert resumed_count == 2
        assert {call.args[0] for call in mock_spawn.call_args_list} == {queued.id, running.id}


class TestEnsureProject:
    @pytest.mark.asyncio
    async def test_creates_project_when_none(self, db_session):
        from src.app.services.simulation_dispatcher import _ensure_project

        sim = await _create_simulation(
            db_session,
            mode="standard", prompt_text="test prompt",
            template_name="g", execution_profile="preview",
        )

        project_id = await _ensure_project(db_session, sim)
        assert project_id is not None

        from src.app.models.project import Project
        project = await db_session.get(Project, project_id)
        assert project is not None
        assert project.prompt_text == "test prompt"

    @pytest.mark.asyncio
    async def test_returns_existing_project(self, db_session):
        from src.app.models.project import Project
        from src.app.services.simulation_dispatcher import _ensure_project
        import uuid

        project = Project(id=str(uuid.uuid4()), name="existing", prompt_text="existing prompt")
        db_session.add(project)
        await db_session.commit()

        sim = await _create_simulation(
            db_session,
            mode="standard", prompt_text="test",
            template_name="g", execution_profile="preview",
        )
        sim.project_id = project.id
        await db_session.commit()

        result_id = await _ensure_project(db_session, sim)
        assert result_id == project.id
