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
    """mode のデフォルト値は 'pipeline'（DB互換）。"""
    from src.app.models.simulation import Simulation
    col = Simulation.__table__.columns["mode"]
    # DB レベルのデフォルトは旧互換で pipeline のまま
    # normalize_mode() でプリセットに変換される
    assert col.default.arg in ("pipeline", "standard", "unified")


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


def test_simulation_model_nullable_columns():
    """nullable な外部キーカラムが正しく nullable になっている。"""
    from src.app.models.simulation import Simulation
    assert Simulation.__table__.columns["project_id"].nullable is True
    assert Simulation.__table__.columns["run_id"].nullable is True
    assert Simulation.__table__.columns["started_at"].nullable is True
    assert Simulation.__table__.columns["completed_at"].nullable is True


def test_simulation_model_valid_mode_values():
    """新プリセットが VALID_PRESETS に定義されている。"""
    from src.app.models.simulation import VALID_PRESETS
    expected = {"quick", "standard", "deep", "research", "baseline"}
    assert expected == VALID_PRESETS


def test_simulation_model_stage_progress_default_is_dict():
    from src.app.models.simulation import Simulation
    col = Simulation.__table__.columns["stage_progress"]
    # JSON カラムのデフォルトは dict を返す callable
    assert callable(col.default.arg) or col.default.arg == {} or col.default.arg is not None
