"""Phase 8: 自動キャリブレーション学習ループのテスト。

ドメイン別バイアスプロファイルを観測データから学習し、
分布補正・回帰検出ができることを確認する。
"""

from __future__ import annotations

import pytest

from src.app.models.calibration_profile import CalibrationProfile
from src.app.services.society.calibration_learner import CalibrationLearner


STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


def _make_observation(predicted: dict[str, float], observed: dict[str, float]) -> dict:
    return {"predicted": dict(predicted), "observed": dict(observed)}


def _biased_observations(n: int, bias: float = 0.2) -> list[dict]:
    """predicted は '賛成' に bias だけ偏らせた分布、observed はフラット."""
    obs = []
    for i in range(n):
        # 予測は systematic に '賛成' を過大評価
        predicted = {
            "賛成": 0.4 + bias,
            "条件付き賛成": 0.2,
            "中立": 0.2 - bias / 2,
            "条件付き反対": 0.1,
            "反対": 0.1 - bias / 2,
        }
        # 実際の観測は均等寄り
        observed = {
            "賛成": 0.4,
            "条件付き賛成": 0.2,
            "中立": 0.2,
            "条件付き反対": 0.1,
            "反対": 0.1,
        }
        obs.append(_make_observation(predicted, observed))
    return obs


def test_calibration_profile_round_trip() -> None:
    """CalibrationProfile は to_dict/from_dict で JSON ラウンドトリップできる."""
    profile = CalibrationProfile(
        domain="welfare",
        bias_profile={"賛成": 0.1, "反対": -0.05},
        ece=0.07,
        sample_count=12,
        updated_at="2026-05-07T00:00:00",
    )
    restored = CalibrationProfile.from_dict(profile.to_dict())
    assert restored == profile


def test_bias_profile_updates_after_observations() -> None:
    """observations を学習するとプロファイルの bias が観測偏差を反映する."""
    learner = CalibrationLearner(min_samples=3)
    obs = _biased_observations(10, bias=0.2)

    profile = learner.learn_from_observations("welfare", obs)

    assert profile.domain == "welfare"
    assert profile.sample_count == 10
    # '賛成' は予測が観測より +0.2 ズレているので bias > 0 になるはず
    assert profile.bias_profile["賛成"] == pytest.approx(0.2, abs=1e-6)
    # 中立側は予測が観測より低めなので bias < 0
    assert profile.bias_profile["中立"] == pytest.approx(-0.1, abs=1e-6)
    assert isinstance(profile.updated_at, str)
    assert profile.updated_at  # 非空 ISO timestamp


def test_apply_calibration_moves_distribution_toward_observed() -> None:
    """apply_calibration は predicted を observed 側へ近づける."""
    learner = CalibrationLearner(min_samples=3)
    obs = _biased_observations(10, bias=0.2)
    profile = learner.learn_from_observations("welfare", obs)

    raw = {
        "賛成": 0.6,
        "条件付き賛成": 0.2,
        "中立": 0.1,
        "条件付き反対": 0.05,
        "反対": 0.05,
    }
    calibrated = learner.apply_calibration(raw, profile)

    # 合計1.0 に正規化
    assert sum(calibrated.values()) == pytest.approx(1.0, abs=1e-6)
    # 全て 0 以上
    assert all(v >= 0.0 for v in calibrated.values())
    # 賛成（過大評価）の bias を引いた結果、raw より小さくなる
    assert calibrated["賛成"] < raw["賛成"]


def test_domain_specific_profiles_are_isolated() -> None:
    """ドメインが違えば独立したプロファイルになる."""
    learner = CalibrationLearner(min_samples=3)

    welfare_obs = _biased_observations(8, bias=0.2)  # 賛成 +0.2
    economy_obs = _biased_observations(8, bias=-0.15)  # 賛成 -0.15

    welfare = learner.learn_from_observations("welfare", welfare_obs)
    economy = learner.learn_from_observations("economy", economy_obs)

    assert welfare.domain == "welfare"
    assert economy.domain == "economy"
    assert welfare.bias_profile["賛成"] == pytest.approx(0.2, abs=1e-6)
    assert economy.bias_profile["賛成"] == pytest.approx(-0.15, abs=1e-6)
    # 互いに独立: welfare の補正適用は economy の bias に影響されない
    raw = {s: 0.2 for s in STANCES}
    cal_w = learner.apply_calibration(raw, welfare)
    cal_e = learner.apply_calibration(raw, economy)
    assert cal_w != cal_e


def test_train_test_split_is_deterministic_with_fixed_seed() -> None:
    """同じ seed なら毎回同じ train/test 分割になる."""
    learner = CalibrationLearner()
    # 各 observation を id で区別できるようにする
    obs = [
        {"id": i, "predicted": {"賛成": 0.5}, "observed": {"賛成": 0.5}}
        for i in range(20)
    ]

    train1, test1 = learner.train_test_split(obs, test_ratio=0.3, seed=42)
    train2, test2 = learner.train_test_split(obs, test_ratio=0.3, seed=42)

    assert [o["id"] for o in train1] == [o["id"] for o in train2]
    assert [o["id"] for o in test1] == [o["id"] for o in test2]
    # 比率の確認
    assert len(test1) == 6  # 20 * 0.3
    assert len(train1) == 14
    # 異なる seed なら順序/中身が変わるはず
    train3, test3 = learner.train_test_split(obs, test_ratio=0.3, seed=99)
    assert (
        [o["id"] for o in train1] != [o["id"] for o in train3]
        or [o["id"] for o in test1] != [o["id"] for o in test3]
    )


def test_ece_improves_after_calibration_on_biased_predictor() -> None:
    """偏った predictor をキャリブレートすると ECE が改善する."""
    learner = CalibrationLearner(min_samples=3)
    obs = _biased_observations(30, bias=0.2)

    train, test = learner.train_test_split(obs, test_ratio=0.3, seed=0)
    profile = learner.learn_from_observations("welfare", train)
    metrics = learner.evaluate(profile, test)

    assert "ece_before" in metrics
    assert "ece_after" in metrics
    assert "improvement" in metrics
    # ECE が None でない（テストデータがある）
    assert metrics["ece_before"] is not None
    assert metrics["ece_after"] is not None
    # キャリブレーション後の ECE は等しいかそれ以下
    assert metrics["ece_after"] <= metrics["ece_before"] + 1e-9
    # improvement = before - after
    assert metrics["improvement"] == pytest.approx(
        metrics["ece_before"] - metrics["ece_after"], abs=1e-9
    )


def test_min_samples_guard_returns_zero_bias() -> None:
    """min_samples 未満のときは bias を学習せず ゼロプロファイルを返す."""
    learner = CalibrationLearner(min_samples=5)
    obs = _biased_observations(2, bias=0.3)

    profile = learner.learn_from_observations("welfare", obs)

    assert profile.sample_count == 2
    # 学習データ不足: bias_profile は全スタンスゼロ
    assert all(v == 0.0 for v in profile.bias_profile.values())
