"""HorizonalCalibrator: 各 horizon (t0..t5) ごとに CalibrationLearner を適用するヘルパー."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from src.app.models.calibration_profile import CalibrationProfile
from src.app.services.society.calibration_learner import CalibrationLearner
from src.app.services.society.time_axis_orchestrator import TimeStep, TimeStepSnapshot


class HorizonalCalibrator:
    """Per-horizon calibration applier composed with CalibrationLearner."""

    def __init__(self, learner: CalibrationLearner | None = None) -> None:
        """fresh CalibrationLearner をデフォルトで使う."""
        self.learner = learner if learner is not None else CalibrationLearner()

    def train_per_horizon(
        self,
        observations_by_horizon: dict[str, list[dict]],
        domain: str = "default",
    ) -> dict[str, CalibrationProfile]:
        """horizon_key -> CalibrationProfile を返す (min_samples 未満は除外)."""
        profiles: dict[str, CalibrationProfile] = {}
        min_samples = self.learner.min_samples
        for key, observations in observations_by_horizon.items():
            if not observations or len(observations) < min_samples:
                continue
            profiles[key] = self.learner.learn_from_observations(domain, observations)
        return profiles

    def calibrate_snapshot(
        self,
        snapshot: TimeStepSnapshot,
        profiles: dict[str, CalibrationProfile],
    ) -> TimeStepSnapshot:
        """profiles[snapshot.step.key] で distribution を補正した新 snapshot を返す."""
        profile = profiles.get(snapshot.step.key)
        if profile is None:
            # passthrough: shallow-copy mutable fields so caller can't share refs
            return replace(
                snapshot,
                distribution=dict(snapshot.distribution),
                metadata=dict(snapshot.metadata) if snapshot.metadata is not None else None,
                market_prices=(
                    list(snapshot.market_prices) if snapshot.market_prices is not None else None
                ),
            )

        calibrated = self.learner.apply_calibration(snapshot.distribution, profile)
        new_metadata: dict = dict(snapshot.metadata) if snapshot.metadata else {}
        new_metadata["calibrated"] = True
        new_metadata["calibration_ece"] = float(profile.ece)
        return replace(
            snapshot,
            distribution=calibrated,
            metadata=new_metadata,
            market_prices=(
                list(snapshot.market_prices) if snapshot.market_prices is not None else None
            ),
        )

    def calibrate_pipeline(
        self,
        snapshots: list[TimeStepSnapshot],
        profiles: dict[str, CalibrationProfile],
    ) -> list[TimeStepSnapshot]:
        """各 snapshot に calibrate_snapshot を適用した新リストを返す (純関数)."""
        return [self.calibrate_snapshot(s, profiles) for s in snapshots]

    def make_orchestrator_hook(
        self,
        profiles: dict[str, CalibrationProfile],
    ) -> Callable[[TimeStep, TimeStepSnapshot], None]:
        """TimeAxisOrchestrator(on_step_completed=...) 用の in-place mutating フックを返す."""

        learner = self.learner

        def _hook(step: TimeStep, snapshot: TimeStepSnapshot) -> None:
            """対応する profile があれば snapshot を in-place で書き換える."""
            profile = profiles.get(step.key)
            if profile is None:
                return
            snapshot.distribution = learner.apply_calibration(snapshot.distribution, profile)
            meta = dict(snapshot.metadata) if snapshot.metadata else {}
            meta["calibrated"] = True
            meta["calibration_ece"] = float(profile.ece)
            snapshot.metadata = meta

        return _hook
