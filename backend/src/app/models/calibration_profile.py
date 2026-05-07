"""CalibrationProfile: ドメイン別キャリブレーションプロファイル（純データクラス）。

Phase 8 ではまず純粋な Python dataclass として導入し、JSON ラウンドトリップに対応する。
DB 永続化（SQLAlchemy 化）は後続フェーズで `database.py` と合わせて行う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CalibrationProfile:
    """ドメイン別キャリブレーションプロファイル。

    Attributes:
        domain: トピック/ドメイン識別子（例: "welfare"）。
        bias_profile: スタンス別 bias multiplier。`predicted - observed` の平均。
        ece: 学習データに対する期待キャリブレーション誤差。
        sample_count: 学習に使った観測サンプル数。
        updated_at: ISO8601 タイムスタンプ文字列。
    """

    domain: str
    bias_profile: dict[str, float] = field(default_factory=dict)
    ece: float = 0.0
    sample_count: int = 0
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """JSON シリアライズ可能な dict に変換する。"""
        return {
            "domain": self.domain,
            "bias_profile": dict(self.bias_profile),
            "ece": float(self.ece),
            "sample_count": int(self.sample_count),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalibrationProfile":
        """dict からプロファイルを復元する。"""
        return cls(
            domain=str(data["domain"]),
            bias_profile={str(k): float(v) for k, v in data.get("bias_profile", {}).items()},
            ece=float(data.get("ece", 0.0)),
            sample_count=int(data.get("sample_count", 0)),
            updated_at=str(data.get("updated_at", "")),
        )
