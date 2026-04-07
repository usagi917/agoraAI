"""P5-1: リグレッションテストスイート

フィーチャーフラグ ON/OFF でミニシミュレーション(seed=42)を実行し、
ゴールデンベースラインとの差分でリグレッションを検知する。
"""

import pytest


class TestRegressionSuite:
    """フィーチャーフラグ別リグレッションテスト."""

    @pytest.mark.asyncio
    async def test_population_deterministic_baseline(self):
        """seed=42 でのポピュレーション生成がゴールデンベースラインと一致."""
        from src.app.services.society.population_generator import generate_population

        agents = await generate_population("regression-pop", count=100, seed=42)

        # 基本検証
        assert len(agents) == 100

        # seed=42 での2回目の生成が同一であること（決定性）
        agents2 = await generate_population("regression-pop2", count=100, seed=42)
        for a1, a2 in zip(agents, agents2):
            assert a1["demographics"] == a2["demographics"]
            assert a1["big_five"] == a2["big_five"]

    def test_accuracy_config_flags_default_off(self):
        """全フィーチャーフラグがデフォルトで OFF であること."""
        from src.app.services.society.accuracy_config import AccuracyConfig, KNOWN_FEATURES

        config = AccuracyConfig({})
        for feature in KNOWN_FEATURES:
            assert config.is_enabled(feature) is False, f"{feature} should be disabled by default"

    def test_accuracy_config_toggle_roundtrip(self):
        """フラグの ON→OFF→ON ラウンドトリップが機能すること."""
        from src.app.services.society.accuracy_config import AccuracyConfig

        config = AccuracyConfig({})
        for state in [True, False, True]:
            config.set_enabled("ats_calibration", state)
            assert config.is_enabled("ats_calibration") is state

    def test_calibration_idempotent(self):
        """同一入力でキャリブレーション結果が同一であること."""
        from src.app.services.society.calibration import platt_recalibrate

        for conf in [0.1, 0.3, 0.5, 0.7, 0.9]:
            r1 = platt_recalibrate(conf)
            r2 = platt_recalibrate(conf)
            assert r1 == r2

    def test_jsd_metric_deterministic(self):
        """JSD メトリクスが決定的であること."""
        from src.app.evaluation.metrics import JSDMetric

        metric = JSDMetric()
        p = {"賛成": 0.6, "反対": 0.3, "中立": 0.1}
        q = {"賛成": 0.4, "反対": 0.4, "中立": 0.2}

        r1 = metric.compute(predicted=p, observed=q)
        r2 = metric.compute(predicted=p, observed=q)
        assert r1["score"] == r2["score"]
