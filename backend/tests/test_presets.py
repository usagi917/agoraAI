"""プリセット定義とモード正規化のテスト"""

import pytest


class TestPresets:
    def test_quick_has_2_phases(self):
        from src.app.models.simulation import PRESETS
        assert len(PRESETS["quick"]) == 2

    def test_standard_has_3_phases(self):
        from src.app.models.simulation import PRESETS
        assert len(PRESETS["standard"]) == 3

    def test_deep_has_5_phases(self):
        from src.app.models.simulation import PRESETS
        assert len(PRESETS["deep"]) == 5

    def test_research_has_5_phases(self):
        from src.app.models.simulation import PRESETS
        assert len(PRESETS["research"]) == 5

    def test_baseline_is_special(self):
        from src.app.models.simulation import PRESETS
        assert "baseline" not in PRESETS  # baseline は separate orchestrator

    def test_quick_phases(self):
        from src.app.models.simulation import PRESETS
        assert PRESETS["quick"] == ["society_pulse", "synthesis"]

    def test_standard_phases(self):
        from src.app.models.simulation import PRESETS
        assert PRESETS["standard"] == ["society_pulse", "council", "synthesis"]

    def test_deep_phases(self):
        from src.app.models.simulation import PRESETS
        phases = PRESETS["deep"]
        assert "society_pulse" in phases
        assert "multi_perspective" in phases
        assert "council" in phases
        assert "pm_analysis" in phases
        assert "synthesis" in phases

    def test_research_phases(self):
        from src.app.models.simulation import PRESETS
        phases = PRESETS["research"]
        assert "society_pulse" in phases
        assert "issue_mining" in phases
        assert "intervention" in phases
        assert "synthesis" in phases


class TestNormalizeMode:
    @pytest.mark.parametrize("mode", ["quick", "standard", "deep", "research", "baseline"])
    def test_valid_preset_accepted(self, mode):
        from src.app.models.simulation import normalize_mode
        assert normalize_mode(mode) == mode

    @pytest.mark.parametrize("old_mode,expected", [
        ("pipeline", "deep"),
        ("swarm", "deep"),
        ("hybrid", "deep"),
        ("pm_board", "deep"),
        ("single", "quick"),
        ("society", "standard"),
        ("society_first", "research"),
        ("meta_simulation", "research"),
        ("unified", "standard"),
    ])
    def test_old_mode_remaps(self, old_mode, expected):
        from src.app.models.simulation import normalize_mode
        assert normalize_mode(old_mode) == expected

    def test_unknown_mode_raises(self):
        from src.app.models.simulation import normalize_mode
        with pytest.raises(ValueError, match="Unknown mode"):
            normalize_mode("invalid_mode_xyz")
