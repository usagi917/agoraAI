"""精度改善フィーチャーフラグとキャリブレーション・アーティファクト保存

population_mix.yaml の accuracy_improvements セクションからフラグを読み取る。
各フラグはデフォルトで false。ランタイムでの切替も可能。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 既知のフィーチャーフラグ一覧
KNOWN_FEATURES: set[str] = {
    "ats_calibration",
    "conformal_prediction",
    "ensemble_aggregation",
    "single_llm_ensemble",
    "heterogeneous_thresholds",
    "memory_anchor",
    "confirmation_bias",
    "bayesian_param_opt",
    "event_loss_aversion",
    "event_two_phase_decay",
    "follower_dynamics",
    "ipf_population_weights",
    "ipf_joint_sampling",
    "post_propagation_market",
    "mrp_estimation",
    "theory_of_mind_cot",
    "filter_bubble_width",
    "agreeableness_in_dynamics",
    "hybrid_network",
    "post_activation_persona",
    "meeting_feedback_propagation",
    "episodic_memory",
    "rolling_summary",
    # Wondrous Prancing Crayon: 高精度群知能市場シミュレーション
    "time_axis_orchestrator",
    "population_drift",
    "bayesian_belief_update",
    "monte_carlo_ensemble",
    "cascade_propagation",
    "multi_outcome_market",
    "calibration_learner",
    "diversity_enforcement",
    "temporal_report",
}


class AccuracyConfig:
    """フィーチャーフラグ管理."""

    def __init__(self, mix_config: dict[str, Any]) -> None:
        section = mix_config.get("accuracy_improvements", {})
        self._flags: dict[str, bool] = {
            k: bool(section.get(k, False)) for k in KNOWN_FEATURES
        }

    def is_enabled(self, feature: str) -> bool:
        return self._flags.get(feature, False)

    def set_enabled(self, feature: str, enabled: bool) -> None:
        self._flags[feature] = enabled


def is_enabled(feature: str) -> bool:
    """モジュールレベル便利関数: population_mix.yaml から直接フラグを読む."""
    import logging
    logger = logging.getLogger(__name__)
    if feature not in KNOWN_FEATURES:
        raise ValueError(
            f"Unknown accuracy feature '{feature}'. "
            f"Register it in accuracy_config.KNOWN_FEATURES first."
        )
    try:
        from src.app.config import settings
        config = settings.load_population_mix_config()
        section = config.get("accuracy_improvements", {})
        return bool(section.get(feature, False))
    except Exception as exc:
        logger.warning("Failed to load accuracy flags: %s", exc)
        return False


class CalibrationArtifactStore:
    """トピック別 shrink factor 等のキャリブレーション結果を JSON で保存/読込."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self._base_dir / f"{name}.json"

    def save(self, name: str, data: dict) -> None:
        with open(self._path(name), "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, name: str) -> dict | None:
        path = self._path(name)
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)
