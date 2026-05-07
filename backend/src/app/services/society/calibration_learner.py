"""自動キャリブレーション学習ループ（Phase 8）。

ドメイン別の観測データから per-stance bias と ECE を学習し、
分布補正・回帰検出（before/after ECE）を提供する。

DB 永続化や API 統合は後続フェーズで行う（このモジュールは純ロジックのみ）。
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from src.app.models.calibration_profile import CalibrationProfile
from src.app.services.society.calibration import expected_calibration_error
from src.app.services.society.constants import STANCE_ORDER as STANCES


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_ece_pairs(predicted: dict[str, float], observed: dict[str, float]) -> list[tuple[float, bool]]:
    """(predicted, observed) 分布から ECE 用の (p, did_happen) ペアに変換する。

    近似: スタンスごとに observed_k >= predicted_k なら "起きた" とみなす（決定的閾値）。
    """
    pairs: list[tuple[float, bool]] = []
    for stance in STANCES:
        p = float(predicted.get(stance, 0.0))
        o = float(observed.get(stance, 0.0))
        pairs.append((p, o >= p))
    return pairs


class CalibrationLearner:
    """観測データから per-stance bias を学習し補正・評価を行うクラス。"""

    def __init__(self, min_samples: int = 5) -> None:
        self.min_samples = max(1, int(min_samples))

    # ---------------------------------------------------------------- learn
    def learn_from_observations(
        self,
        domain: str,
        observations: list[dict],
    ) -> CalibrationProfile:
        """観測データからキャリブレーションプロファイルを学習する。

        各 observation は {"predicted": dict, "observed": dict}。
        per-stance bias は mean(predicted_k - observed_k)。
        """
        n = len(observations)
        if n == 0 or n < self.min_samples:
            return CalibrationProfile(
                domain=domain,
                bias_profile={s: 0.0 for s in STANCES},
                ece=0.0,
                sample_count=n,
                updated_at=_now_iso(),
            )

        # per-stance 偏差合計
        sums: dict[str, float] = {s: 0.0 for s in STANCES}
        for obs in observations:
            predicted = obs["predicted"]
            observed = obs["observed"]
            for stance in STANCES:
                sums[stance] += float(predicted.get(stance, 0.0)) - float(observed.get(stance, 0.0))

        bias = {s: sums[s] / n for s in STANCES}

        # 学習データ上での calibrated 分布から ECE を計算
        profile_for_ece = CalibrationProfile(
            domain=domain,
            bias_profile=bias,
            ece=0.0,
            sample_count=n,
            updated_at="",
        )
        all_pairs: list[tuple[float, bool]] = []
        for obs in observations:
            calibrated = self.apply_calibration(obs["predicted"], profile_for_ece)
            all_pairs.extend(_to_ece_pairs(calibrated, obs["observed"]))
        ece = expected_calibration_error(all_pairs) or 0.0

        return CalibrationProfile(
            domain=domain,
            bias_profile=bias,
            ece=float(ece),
            sample_count=n,
            updated_at=_now_iso(),
        )

    # ---------------------------------------------------------------- apply
    def apply_calibration(
        self,
        distribution: dict[str, float],
        profile: CalibrationProfile,
    ) -> dict[str, float]:
        """bias を引いて 0 にクリップ、合計 1.0 に再正規化する。"""
        adjusted: dict[str, float] = {}
        for stance in STANCES:
            raw = float(distribution.get(stance, 0.0))
            b = float(profile.bias_profile.get(stance, 0.0))
            adjusted[stance] = max(0.0, raw - b)

        total = sum(adjusted.values())
        if total > 0:
            return {k: v / total for k, v in adjusted.items()}
        # 全部ゼロになったらフラット分布にフォールバック
        flat = 1.0 / len(STANCES)
        return {s: flat for s in STANCES}

    # ---------------------------------------------------------------- split
    def train_test_split(
        self,
        observations: list[dict],
        test_ratio: float = 0.3,
        seed: int = 0,
    ) -> tuple[list[dict], list[dict]]:
        """seed 固定の決定的シャッフルで train/test に分割する。"""
        if not observations:
            return [], []
        rng = random.Random(seed)
        indices = list(range(len(observations)))
        rng.shuffle(indices)
        n_test = int(len(observations) * test_ratio)
        test_idx = set(indices[:n_test])
        train = [observations[i] for i in range(len(observations)) if i not in test_idx]
        test = [observations[i] for i in range(len(observations)) if i in test_idx]
        return train, test

    # ------------------------------------------------------------- evaluate
    def evaluate(
        self,
        profile: CalibrationProfile,
        test_obs: list[dict],
    ) -> dict:
        """test_obs に対する キャリブ前後の ECE と improvement を返す。"""
        before_pairs: list[tuple[float, bool]] = []
        after_pairs: list[tuple[float, bool]] = []
        for obs in test_obs:
            predicted = obs["predicted"]
            observed = obs["observed"]
            before_pairs.extend(_to_ece_pairs(predicted, observed))
            calibrated = self.apply_calibration(predicted, profile)
            after_pairs.extend(_to_ece_pairs(calibrated, observed))

        ece_before = expected_calibration_error(before_pairs)
        ece_after = expected_calibration_error(after_pairs)
        improvement = (
            (ece_before - ece_after)
            if (ece_before is not None and ece_after is not None)
            else None
        )
        return {
            "ece_before": ece_before,
            "ece_after": ece_after,
            "improvement": improvement,
        }
