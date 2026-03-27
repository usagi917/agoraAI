"""BaseMetric: 評価メトリクスの抽象基底クラス"""

from abc import ABC, abstractmethod
from typing import Any


class BaseMetric(ABC):
    """全メトリクスの共通インターフェース。

    サブクラスは name, description を定義し、compute() を実装する。
    compute() は {"score": float, "details": dict} を返す。
    """

    name: str
    description: str

    @abstractmethod
    def compute(self, **kwargs: Any) -> dict:
        """メトリクスを計算する。

        Returns:
            {"score": float, "details": dict}
        """
