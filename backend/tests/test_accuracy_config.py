"""P1-3: accuracy_config.py のテスト"""

import json
import os
import tempfile

import pytest


class TestAccuracyConfig:
    """フィーチャーフラグの有効化/無効化テスト."""

    def test_default_all_disabled(self):
        """デフォルトではすべてのフィーチャーフラグが無効."""
        from src.app.services.society.accuracy_config import AccuracyConfig

        config = AccuracyConfig({})
        assert config.is_enabled("ats_calibration") is False
        assert config.is_enabled("conformal_prediction") is False
        assert config.is_enabled("ensemble_aggregation") is False

    def test_enable_feature(self):
        """population_mix config からフラグを有効化できること."""
        from src.app.services.society.accuracy_config import AccuracyConfig

        mix_config = {
            "accuracy_improvements": {
                "ats_calibration": True,
            }
        }
        config = AccuracyConfig(mix_config)
        assert config.is_enabled("ats_calibration") is True
        assert config.is_enabled("conformal_prediction") is False

    def test_set_enabled_runtime(self):
        """ランタイムでフラグを切り替えられること."""
        from src.app.services.society.accuracy_config import AccuracyConfig

        config = AccuracyConfig({})
        assert config.is_enabled("ats_calibration") is False

        config.set_enabled("ats_calibration", True)
        assert config.is_enabled("ats_calibration") is True

        config.set_enabled("ats_calibration", False)
        assert config.is_enabled("ats_calibration") is False

    def test_unknown_feature_returns_false(self):
        """未知のフィーチャー名は常に False."""
        from src.app.services.society.accuracy_config import AccuracyConfig

        config = AccuracyConfig({})
        assert config.is_enabled("nonexistent_feature") is False

    def test_all_known_features(self):
        """既知のフィーチャーフラグ一覧が取得できること."""
        from src.app.services.society.accuracy_config import KNOWN_FEATURES

        assert "ats_calibration" in KNOWN_FEATURES
        assert "conformal_prediction" in KNOWN_FEATURES
        assert "ensemble_aggregation" in KNOWN_FEATURES
        assert "heterogeneous_thresholds" in KNOWN_FEATURES
        assert "confirmation_bias" in KNOWN_FEATURES


class TestCalibrationArtifactStore:
    """CalibrationArtifactStore のテスト."""

    def test_save_and_load(self, tmp_path):
        """保存したアーティファクトを読み込めること."""
        from src.app.services.society.accuracy_config import CalibrationArtifactStore

        store = CalibrationArtifactStore(tmp_path)
        data = {"politics": 0.85, "economy": 0.72}
        store.save("topic_shrink_factors", data)

        loaded = store.load("topic_shrink_factors")
        assert loaded == data

    def test_load_nonexistent_returns_none(self, tmp_path):
        """存在しないアーティファクトの読み込みは None を返す."""
        from src.app.services.society.accuracy_config import CalibrationArtifactStore

        store = CalibrationArtifactStore(tmp_path)
        assert store.load("nonexistent") is None

    def test_overwrite_existing(self, tmp_path):
        """上書き保存が機能すること."""
        from src.app.services.society.accuracy_config import CalibrationArtifactStore

        store = CalibrationArtifactStore(tmp_path)
        store.save("factors", {"a": 1.0})
        store.save("factors", {"a": 2.0})

        loaded = store.load("factors")
        assert loaded == {"a": 2.0}
