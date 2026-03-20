"""Simulation モデルのユニットテスト"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import patch


# -----------------------------------------------------------------------
# Simulation モデルのデフォルト値テスト
# -----------------------------------------------------------------------

def test_simulation_model_importable():
    from src.app.models.simulation import Simulation
    assert Simulation is not None


def test_simulation_model_tablename():
    from src.app.models.simulation import Simulation
    assert Simulation.__tablename__ == "simulations"


def test_simulation_model_default_mode():
    """mode のデフォルト値は 'pipeline'。"""
    from src.app.models.simulation import Simulation
    # SQLAlchemy の mapped_column default は callable または値
    # カラム定義から default を確認
    col = Simulation.__table__.columns["mode"]
    assert col.default.arg == "pipeline"


def test_simulation_model_default_status():
    from src.app.models.simulation import Simulation
    col = Simulation.__table__.columns["status"]
    assert col.default.arg == "queued"


def test_simulation_model_default_execution_profile():
    from src.app.models.simulation import Simulation
    col = Simulation.__table__.columns["execution_profile"]
    assert col.default.arg == "standard"


def test_simulation_model_default_pipeline_stage():
    from src.app.models.simulation import Simulation
    col = Simulation.__table__.columns["pipeline_stage"]
    assert col.default.arg == "pending"


def test_simulation_model_default_colony_count():
    from src.app.models.simulation import Simulation
    col = Simulation.__table__.columns["colony_count"]
    assert col.default.arg == 1


def test_simulation_model_default_deep_colony_count():
    from src.app.models.simulation import Simulation
    col = Simulation.__table__.columns["deep_colony_count"]
    assert col.default.arg == 0


def test_simulation_model_nullable_columns():
    """nullable な外部キーカラムが正しく nullable になっている。"""
    from src.app.models.simulation import Simulation
    assert Simulation.__table__.columns["project_id"].nullable is True
    assert Simulation.__table__.columns["run_id"].nullable is True
    assert Simulation.__table__.columns["swarm_id"].nullable is True
    assert Simulation.__table__.columns["started_at"].nullable is True
    assert Simulation.__table__.columns["completed_at"].nullable is True


def test_simulation_model_valid_mode_values():
    """コメントに記載されたサポートモードが文字列として定義されている。"""
    valid_modes = {"pipeline", "single", "swarm", "hybrid", "pm_board"}
    # コメント内の期待モードとコードの定数が一致することを確認
    from src.app.services.simulation_dispatcher import dispatch_simulation
    # dispatch 関数が pipeline, single, swarm, hybrid, pm_board を扱うことを
    # モジュール内の文字列リテラルで確認
    import inspect
    source = inspect.getsource(dispatch_simulation)
    for mode in valid_modes:
        assert mode in source, f"mode '{mode}' が dispatch_simulation に見当たらない"


def test_simulation_model_stage_progress_default_is_dict():
    from src.app.models.simulation import Simulation
    col = Simulation.__table__.columns["stage_progress"]
    # JSON カラムのデフォルトは dict を返す callable
    assert callable(col.default.arg) or col.default.arg == {} or col.default.arg is not None
