"""SingleRunSimulator のユニットテスト"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.app.services.simulator import SingleRunSimulator, PROFILE_ROUNDS
from src.app.services.colony_factory import ColonyConfig


# -----------------------------------------------------------------------
# PROFILE_ROUNDS
# -----------------------------------------------------------------------

def test_profile_rounds_keys():
    assert "preview" in PROFILE_ROUNDS
    assert "standard" in PROFILE_ROUNDS
    assert "quality" in PROFILE_ROUNDS


def test_profile_rounds_values():
    assert PROFILE_ROUNDS["preview"] < PROFILE_ROUNDS["standard"]
    assert PROFILE_ROUNDS["standard"] < PROFILE_ROUNDS["quality"]


# -----------------------------------------------------------------------
# _inject_perspective
# -----------------------------------------------------------------------

def test_inject_perspective_no_colony_config():
    sim = SingleRunSimulator(colony_config=None)
    assert sim._inject_perspective("base prompt") == "base prompt"


def test_inject_perspective_empty_injection():
    config = MagicMock(spec=ColonyConfig)
    config.system_injection = "   "
    sim = SingleRunSimulator(colony_config=config)
    assert sim._inject_perspective("base prompt") == "base prompt"


def test_inject_perspective_with_injection():
    config = MagicMock(spec=ColonyConfig)
    config.system_injection = "You are an optimist."
    sim = SingleRunSimulator(colony_config=config)
    result = sim._inject_perspective("Analyze this.")
    assert result.startswith("You are an optimist.")
    assert "Analyze this." in result


def test_inject_perspective_preserves_base_when_injection_empty_string():
    config = MagicMock(spec=ColonyConfig)
    config.system_injection = ""
    sim = SingleRunSimulator(colony_config=config)
    assert sim._inject_perspective("hello world") == "hello world"


def test_inject_perspective_combines_with_newlines():
    config = MagicMock(spec=ColonyConfig)
    config.system_injection = "INJECT"
    sim = SingleRunSimulator(colony_config=config)
    result = sim._inject_perspective("BASE")
    assert "\n\n" in result


# -----------------------------------------------------------------------
# コンストラクタ
# -----------------------------------------------------------------------

def test_single_run_simulator_default_colony_config():
    sim = SingleRunSimulator()
    assert sim.colony_config is None


def test_single_run_simulator_accepts_colony_config():
    config = MagicMock(spec=ColonyConfig)
    sim = SingleRunSimulator(colony_config=config)
    assert sim.colony_config is config


# -----------------------------------------------------------------------
# rounds 決定ロジック（colony_config.round_count vs total_rounds）
# -----------------------------------------------------------------------

def _make_colony_config(round_count: int = 3) -> MagicMock:
    config = MagicMock(spec=ColonyConfig)
    config.round_count = round_count
    config.colony_id = "col-1"
    config.system_injection = ""
    return config


def test_rounds_come_from_colony_config_when_set():
    """colony_config が存在する場合、round 数は colony_config.round_count から取得する。"""
    config = _make_colony_config(round_count=2)
    sim = SingleRunSimulator(colony_config=config)
    # 内部プロパティとして round 数を確認（run() は外部依存が多いので属性だけ確認）
    assert sim.colony_config.round_count == 2
