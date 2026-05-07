"""HorizonalCalibrator: 各 horizon (t0..t5) ごとに CalibrationLearner を適用するヘルパーのテスト."""

from __future__ import annotations

import copy

import pytest

from src.app.models.calibration_profile import CalibrationProfile
from src.app.services.society.calibration_learner import CalibrationLearner
from src.app.services.society.horizonal_calibrator import HorizonalCalibrator
from src.app.services.society.time_axis_orchestrator import (
    DEFAULT_HORIZONS,
    TimeStepSnapshot,
)


STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


def _make_observation(predicted: dict[str, float], observed: dict[str, float]) -> dict:
    return {"predicted": dict(predicted), "observed": dict(observed)}


def _biased_observations(n: int, bias: float = 0.2) -> list[dict]:
    """predicted は '賛成' に bias だけ偏らせた分布、observed はフラット."""
    obs = []
    for _ in range(n):
        predicted = {
            "賛成": 0.4 + bias,
            "条件付き賛成": 0.2,
            "中立": 0.2 - bias / 2,
            "条件付き反対": 0.1,
            "反対": 0.1 - bias / 2,
        }
        observed = {
            "賛成": 0.4,
            "条件付き賛成": 0.2,
            "中立": 0.2,
            "条件付き反対": 0.1,
            "反対": 0.1,
        }
        obs.append(_make_observation(predicted, observed))
    return obs


def _step_by_key(key: str):
    for h in DEFAULT_HORIZONS:
        if h.key == key:
            return h
    raise KeyError(key)


def test_train_per_horizon_returns_profile_for_each_horizon() -> None:
    """各 horizon に十分な観測があれば horizon_key -> profile の dict を返す."""
    learner = CalibrationLearner(min_samples=3)
    calibrator = HorizonalCalibrator(learner)
    obs_by_h = {
        "t0": _biased_observations(6, bias=0.2),
        "t1": _biased_observations(6, bias=0.15),
        "t2": _biased_observations(6, bias=0.1),
    }

    profiles = calibrator.train_per_horizon(obs_by_h, domain="welfare")

    assert set(profiles.keys()) == {"t0", "t1", "t2"}
    for key, prof in profiles.items():
        assert isinstance(prof, CalibrationProfile)
        assert prof.domain == "welfare"
        assert prof.sample_count == 6
    assert profiles["t0"].bias_profile["賛成"] == pytest.approx(0.2, abs=1e-6)
    assert profiles["t1"].bias_profile["賛成"] == pytest.approx(0.15, abs=1e-6)


def test_train_per_horizon_skips_horizons_below_min_samples() -> None:
    """min_samples 未満の horizon は結果から除外される."""
    learner = CalibrationLearner(min_samples=5)
    calibrator = HorizonalCalibrator(learner)
    obs_by_h = {
        "t0": _biased_observations(8, bias=0.2),
        "t1": _biased_observations(2, bias=0.2),  # too few
        "t2": _biased_observations(6, bias=0.1),
    }

    profiles = calibrator.train_per_horizon(obs_by_h, domain="welfare")

    assert set(profiles.keys()) == {"t0", "t2"}
    assert "t1" not in profiles


def test_calibrate_snapshot_does_not_mutate_input() -> None:
    """calibrate_snapshot は入力 snapshot を mutate しない."""
    learner = CalibrationLearner(min_samples=3)
    calibrator = HorizonalCalibrator(learner)
    obs = _biased_observations(8, bias=0.2)
    profile = learner.learn_from_observations("welfare", obs)
    profiles = {"t0": profile}

    raw_dist = {
        "賛成": 0.6,
        "条件付き賛成": 0.2,
        "中立": 0.1,
        "条件付き反対": 0.05,
        "反対": 0.05,
    }
    snapshot = TimeStepSnapshot(
        step=_step_by_key("t0"),
        state={"foo": "bar"},
        distribution=dict(raw_dist),
        market_prices=[0.6, 0.4],
        metadata={"existing": 1},
    )
    snap_before = copy.deepcopy(snapshot)

    new_snap = calibrator.calibrate_snapshot(snapshot, profiles)

    # input untouched
    assert snapshot.distribution == snap_before.distribution
    assert snapshot.metadata == snap_before.metadata
    # new snapshot has calibrated distribution
    assert new_snap is not snapshot
    assert new_snap.distribution != snapshot.distribution
    assert new_snap.distribution["賛成"] < raw_dist["賛成"]
    assert new_snap.metadata is not None
    assert new_snap.metadata["calibrated"] is True
    assert new_snap.metadata["calibration_ece"] == pytest.approx(profile.ece, abs=1e-12)
    assert new_snap.metadata["existing"] == 1
    # untouched fields
    assert new_snap.step == snapshot.step
    assert new_snap.state == snapshot.state
    assert new_snap.market_prices == snapshot.market_prices


def test_calibrate_snapshot_passthrough_when_no_profile() -> None:
    """対応する horizon のプロファイルが無いときは distribution を変えない."""
    calibrator = HorizonalCalibrator()
    raw_dist = {s: 0.2 for s in STANCES}
    snapshot = TimeStepSnapshot(
        step=_step_by_key("t3"),
        state={},
        distribution=dict(raw_dist),
        metadata={"keep": "yes"},
    )

    new_snap = calibrator.calibrate_snapshot(snapshot, profiles={})

    assert new_snap.distribution == raw_dist
    # metadata は維持され、calibrated フラグは付かない
    assert new_snap.metadata == {"keep": "yes"}


def test_calibrate_pipeline_reduces_mean_error_on_biased_predictor() -> None:
    """biased predictor を pipeline 全体に適用すると |predicted-observed| が縮む."""
    learner = CalibrationLearner(min_samples=3)
    calibrator = HorizonalCalibrator(learner)
    horizons = [h.key for h in DEFAULT_HORIZONS]

    obs_by_h = {h: _biased_observations(10, bias=0.2) for h in horizons}
    profiles = calibrator.train_per_horizon(obs_by_h, domain="welfare")

    # 1 つの biased predicted を全 horizon に流す
    biased_pred = {
        "賛成": 0.6,
        "条件付き賛成": 0.2,
        "中立": 0.1,
        "条件付き反対": 0.05,
        "反対": 0.05,
    }
    flat_observed = {
        "賛成": 0.4,
        "条件付き賛成": 0.2,
        "中立": 0.2,
        "条件付き反対": 0.1,
        "反対": 0.1,
    }
    snapshots = [
        TimeStepSnapshot(step=h, state={}, distribution=dict(biased_pred))
        for h in DEFAULT_HORIZONS
    ]

    calibrated = calibrator.calibrate_pipeline(snapshots, profiles)
    assert len(calibrated) == len(snapshots)

    def mean_abs_err(snaps: list[TimeStepSnapshot]) -> float:
        total = 0.0
        n = 0
        for snap in snaps:
            for s in STANCES:
                total += abs(snap.distribution.get(s, 0.0) - flat_observed[s])
                n += 1
        return total / n if n else 0.0

    raw_err = mean_abs_err(snapshots)
    cal_err = mean_abs_err(calibrated)
    assert cal_err < raw_err


def test_make_orchestrator_hook_mutates_snapshot_in_place() -> None:
    """on_step_completed フック形式は snapshot を in-place で更新する."""
    learner = CalibrationLearner(min_samples=3)
    calibrator = HorizonalCalibrator(learner)
    obs = _biased_observations(8, bias=0.2)
    profile = learner.learn_from_observations("welfare", obs)
    profiles = {"t0": profile}

    hook = calibrator.make_orchestrator_hook(profiles)

    raw_dist = {
        "賛成": 0.6,
        "条件付き賛成": 0.2,
        "中立": 0.1,
        "条件付き反対": 0.05,
        "反対": 0.05,
    }
    step = _step_by_key("t0")
    snapshot = TimeStepSnapshot(
        step=step,
        state={},
        distribution=dict(raw_dist),
        metadata=None,
    )

    result = hook(step, snapshot)

    # mutating hook returns None
    assert result is None
    assert snapshot.distribution["賛成"] < raw_dist["賛成"]
    assert sum(snapshot.distribution.values()) == pytest.approx(1.0, abs=1e-6)
    assert snapshot.metadata is not None
    assert snapshot.metadata["calibrated"] is True
    assert snapshot.metadata["calibration_ece"] == pytest.approx(profile.ece, abs=1e-12)


def test_make_orchestrator_hook_noop_when_horizon_missing() -> None:
    """対応する horizon の profile が無いときは hook は何もしない."""
    calibrator = HorizonalCalibrator()
    hook = calibrator.make_orchestrator_hook(profiles={})

    raw_dist = {s: 0.2 for s in STANCES}
    step = _step_by_key("t4")
    snapshot = TimeStepSnapshot(
        step=step,
        state={},
        distribution=dict(raw_dist),
        metadata={"x": 1},
    )

    hook(step, snapshot)

    assert snapshot.distribution == raw_dist
    assert snapshot.metadata == {"x": 1}
