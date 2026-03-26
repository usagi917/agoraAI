"""Simulation Dispatcher v2 テスト"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


class TestDispatchSimulation:
    @pytest.mark.asyncio
    async def test_dispatch_standard_calls_run_unified(self, db_session):
        from src.app.repositories.simulation_repo import SimulationRepository

        repo = SimulationRepository(db_session)
        sim = await repo.create(
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
        from src.app.repositories.simulation_repo import SimulationRepository

        repo = SimulationRepository(db_session)
        sim = await repo.create(
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
        from src.app.repositories.simulation_repo import SimulationRepository

        repo = SimulationRepository(db_session)
        sim = await repo.create(
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
        updated = await repo.get(sim.id)
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
        from src.app.repositories.simulation_repo import SimulationRepository

        repo = SimulationRepository(db_session)
        sim = await repo.create(
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

        updated = await repo.get(sim.id)
        assert updated.status == "failed"
        assert "LLM error" in updated.error_message


class TestEnsureProject:
    @pytest.mark.asyncio
    async def test_creates_project_when_none(self, db_session):
        from src.app.repositories.simulation_repo import SimulationRepository
        from src.app.services.simulation_dispatcher import _ensure_project

        repo = SimulationRepository(db_session)
        sim = await repo.create(
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
        from src.app.repositories.simulation_repo import SimulationRepository
        from src.app.services.simulation_dispatcher import _ensure_project
        import uuid

        project = Project(id=str(uuid.uuid4()), name="existing", prompt_text="existing prompt")
        db_session.add(project)
        await db_session.commit()

        repo = SimulationRepository(db_session)
        sim = await repo.create(
            mode="standard", prompt_text="test",
            template_name="g", execution_profile="preview",
        )
        sim.project_id = project.id
        await db_session.commit()

        result_id = await _ensure_project(db_session, sim)
        assert result_id == project.id
