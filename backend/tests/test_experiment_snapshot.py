"""ExperimentConfig スナップショット自動記録テスト"""

import pytest
from unittest.mock import patch, MagicMock


class TestSnapshotCapture:
    def test_capture_git_hash(self):
        from src.app.evaluation.snapshot import capture_git_hash

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="abc123def456\n"
            )
            result = capture_git_hash()
            assert result == "abc123def456"

    def test_capture_git_hash_not_git_repo(self):
        from src.app.evaluation.snapshot import capture_git_hash

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            result = capture_git_hash()
            assert result is None

    def test_capture_packages(self):
        from src.app.evaluation.snapshot import capture_packages

        result = capture_packages()
        assert isinstance(result, dict)
        # 少なくとも sqlalchemy は入っているはず
        assert "sqlalchemy" in result or len(result) > 0

    def test_capture_yaml_configs(self):
        from src.app.evaluation.snapshot import capture_yaml_configs

        with patch("builtins.open", side_effect=FileNotFoundError):
            result = capture_yaml_configs()
            # ファイルがなくても空dictを返す
            assert isinstance(result, dict)
            assert result.get("models_yaml") == {}

    @pytest.mark.asyncio
    async def test_save_snapshot(self, db_session):
        from src.app.evaluation.snapshot import save_experiment_snapshot
        from src.app.repositories.simulation_repo import SimulationRepository
        from src.app.models.experiment_config import ExperimentConfig

        sim_repo = SimulationRepository(db_session)
        sim = await sim_repo.create(
            mode="standard", prompt_text="test",
            template_name="g", execution_profile="preview",
        )

        with patch("src.app.evaluation.snapshot.capture_git_hash", return_value="abc123"):
            with patch("src.app.evaluation.snapshot.capture_packages", return_value={"sqlalchemy": "2.0.0"}):
                with patch("src.app.evaluation.snapshot.capture_yaml_configs", return_value={
                    "models_yaml": {"test": True},
                    "cognitive_yaml": {},
                    "graphrag_yaml": {},
                    "llm_providers_yaml": {},
                }):
                    snapshot = await save_experiment_snapshot(db_session, sim.id)

        assert snapshot.simulation_id == sim.id
        assert snapshot.git_commit_hash == "abc123"
        assert snapshot.python_packages == {"sqlalchemy": "2.0.0"}
        assert snapshot.models_yaml == {"test": True}

        # DB に永続化されている
        from sqlalchemy import select
        result = await db_session.execute(
            select(ExperimentConfig).where(ExperimentConfig.simulation_id == sim.id)
        )
        saved = result.scalar_one()
        assert saved.git_commit_hash == "abc123"
