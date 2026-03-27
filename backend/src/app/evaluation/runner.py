"""EvaluationRunner: メトリクス一括実行"""

from typing import Any

from src.app.evaluation.base import BaseMetric
from src.app.evaluation.metrics import (
    DiversityMetric,
    ConsistencyMetric,
    ConvergenceMetric,
    CoverageMetric,
)


class EvaluationRunner:
    """登録済みメトリクスを全実行する。"""

    def __init__(self) -> None:
        self.metrics: list[BaseMetric] = []

    def register(self, metric: BaseMetric) -> None:
        self.metrics.append(metric)

    def run_all(self, **kwargs: Any) -> list[dict]:
        """全メトリクスを実行し、結果リストを返す。"""
        results = []
        for metric in self.metrics:
            result = metric.compute(**kwargs)
            results.append({
                "metric_name": metric.name,
                "score": result["score"],
                "details": result.get("details", {}),
            })
        return results


def create_default_runner() -> EvaluationRunner:
    """標準メトリクス一式を登録した EvaluationRunner を返す。"""
    runner = EvaluationRunner()
    runner.register(DiversityMetric())
    runner.register(ConsistencyMetric())
    runner.register(ConvergenceMetric())
    runner.register(CoverageMetric())
    return runner
