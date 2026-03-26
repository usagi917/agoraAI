"""normalize_mode() の網羅テスト"""

import pytest
from src.app.models.simulation import normalize_mode, PRESETS, VALID_PRESETS, MODE_ALIASES


class TestNormalizeMode:
    @pytest.mark.parametrize("preset", ["quick", "standard", "deep", "research", "baseline"])
    def test_valid_presets_pass_through(self, preset):
        assert normalize_mode(preset) == preset

    @pytest.mark.parametrize("old,expected", [
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
    def test_old_modes_remap(self, old, expected):
        assert normalize_mode(old) == expected

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            normalize_mode("nonexistent")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            normalize_mode("")


class TestPresets:
    def test_quick_has_2_phases(self):
        assert len(PRESETS["quick"]) == 2
        assert PRESETS["quick"] == ["society_pulse", "synthesis"]

    def test_standard_has_3_phases(self):
        assert len(PRESETS["standard"]) == 3

    def test_deep_has_5_phases(self):
        assert len(PRESETS["deep"]) == 5
        assert "multi_perspective" in PRESETS["deep"]
        assert "pm_analysis" in PRESETS["deep"]

    def test_research_has_5_phases(self):
        assert len(PRESETS["research"]) == 5
        assert "issue_mining" in PRESETS["research"]
        assert "intervention" in PRESETS["research"]

    def test_baseline_not_in_presets_dict(self):
        assert "baseline" not in PRESETS
        assert "baseline" in VALID_PRESETS

    def test_all_aliases_map_to_valid_presets(self):
        for alias, target in MODE_ALIASES.items():
            assert target in VALID_PRESETS, f"{alias} -> {target} not in VALID_PRESETS"
