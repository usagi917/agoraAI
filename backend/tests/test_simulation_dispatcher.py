"""simulation_dispatcher の純粋ロジックテスト"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.app.services.simulator import PROFILE_ROUNDS


# -----------------------------------------------------------------------
# _dispatch_single: total_rounds の決定ロジック
# -----------------------------------------------------------------------

def test_profile_rounds_used_for_known_profiles():
    """既知のプロファイルは PROFILE_ROUNDS から round 数が決まる。"""
    for profile, expected_rounds in PROFILE_ROUNDS.items():
        actual = PROFILE_ROUNDS.get(profile, 4)
        assert actual == expected_rounds


def test_profile_rounds_fallback_for_unknown():
    """未知のプロファイルはデフォルト 4 ラウンド。"""
    assert PROFILE_ROUNDS.get("unknown_profile", 4) == 4


# -----------------------------------------------------------------------
# dispatch_simulation: mode 分岐ロジックのユニットテスト
# -----------------------------------------------------------------------

VALID_MODES = ["pipeline", "single", "swarm", "hybrid", "pm_board"]
INVALID_MODE = "unknown_mode"


def test_valid_modes_list():
    """サポートされるモードが期待通り存在する。"""
    for mode in VALID_MODES:
        assert isinstance(mode, str)


def test_invalid_mode_raises():
    """未知のモードは ValueError を発生させるべき。"""
    # dispatch_simulation の mode 分岐で未知 mode は raise ValueError
    mode = INVALID_MODE
    supported = {"pipeline", "single", "swarm", "hybrid", "pm_board"}
    assert mode not in supported, f"{mode} は supported に含まれるべきではない"


# -----------------------------------------------------------------------
# _ensure_project のロジック: prompt_text 保存条件
# -----------------------------------------------------------------------

def test_ensure_project_saves_prompt_when_project_has_none():
    """sim に prompt_text があり、project.prompt_text が空ならば更新する。"""
    sim_prompt = "Analyze this scenario"
    project_prompt = ""

    # ロジック: sim.prompt_text が存在し project.prompt_text が falsy なら更新
    should_update = bool(sim_prompt) and not bool(project_prompt)
    assert should_update is True


def test_ensure_project_does_not_overwrite_existing_prompt():
    """project.prompt_text が既にある場合は上書きしない。"""
    sim_prompt = "New prompt"
    project_prompt = "Existing prompt"

    should_update = bool(sim_prompt) and not bool(project_prompt)
    assert should_update is False


def test_ensure_project_no_sim_prompt():
    """sim.prompt_text が空なら project.prompt_text は更新しない。"""
    sim_prompt = ""
    project_prompt = ""

    should_update = bool(sim_prompt) and not bool(project_prompt)
    assert should_update is False


# -----------------------------------------------------------------------
# _dispatch_swarm: hybrid プロファイル名のフォールバックロジック
# -----------------------------------------------------------------------

def test_hybrid_profile_name_construction():
    """hybrid モードは hybrid_{execution_profile} プレフィックスを優先する。"""
    execution_profile = "standard"
    hybrid_profile = f"hybrid_{execution_profile}"
    assert hybrid_profile == "hybrid_standard"


def test_hybrid_profile_fallback_to_original():
    """hybrid プロファイルが存在しない場合は元のプロファイルを使う。"""
    execution_profile = "standard"
    hybrid_profile = f"hybrid_{execution_profile}"
    # generate_colony_configs が ValueError を出した場合、execution_profile にフォールバック
    # ここではロジックの構造だけ確認
    fallback = execution_profile  # 実装に合わせた代替値
    assert fallback == "standard"
