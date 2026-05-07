"""Phase 4: Monte Carlo Ensemble + 確率帯のテスト"""

from __future__ import annotations

import asyncio

import pytest

STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


class TestEnsembleRunner:
    def test_runs_n_times(self):
        from src.app.services.society.ensemble_runner import EnsembleRunner

        async def predictor(seed):
            return {s: 1 / len(STANCES) for s in STANCES}

        runner = EnsembleRunner(n_runs=10, concurrency=4)
        result = asyncio.run(runner.run(predictor))

        assert result.n == 10
        assert len(result.distributions) == 10

    def test_aggregate_returns_credible_intervals(self):
        from src.app.services.society.ensemble_runner import EnsembleRunner

        # 賛成 を各シードで微妙に揺らす
        async def predictor(seed):
            base = 0.4 + (seed % 5) * 0.02
            others = (1 - base) / 4
            return {
                "賛成": base,
                "条件付き賛成": others,
                "中立": others,
                "条件付き反対": others,
                "反対": others,
            }

        runner = EnsembleRunner(n_runs=30, concurrency=8)
        result = asyncio.run(runner.run(predictor))

        ci = result.credible_intervals()
        # 50/80/95% の 3 レベル
        assert {"50", "80", "95"}.issubset(ci.keys())
        # 各 stance について lower <= median <= upper
        ci50 = ci["50"]["賛成"]
        assert ci50["lower"] <= ci50["median"] <= ci50["upper"]
        # 95 が 50 より広い
        ci95 = ci["95"]["賛成"]
        assert ci95["upper"] - ci95["lower"] >= ci50["upper"] - ci50["lower"]

    def test_concurrency_limit_respected(self):
        """同時実行数が concurrency を超えないこと."""
        from src.app.services.society.ensemble_runner import EnsembleRunner

        in_flight = {"current": 0, "max": 0}

        async def predictor(seed):
            in_flight["current"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["current"])
            await asyncio.sleep(0.01)
            in_flight["current"] -= 1
            return {s: 1 / len(STANCES) for s in STANCES}

        runner = EnsembleRunner(n_runs=20, concurrency=3)
        asyncio.run(runner.run(predictor))

        assert in_flight["max"] <= 3

    def test_mean_distribution_sums_to_one(self):
        from src.app.services.society.ensemble_runner import EnsembleRunner

        async def predictor(seed):
            return {s: 1 / len(STANCES) for s in STANCES}

        runner = EnsembleRunner(n_runs=5, concurrency=2)
        result = asyncio.run(runner.run(predictor))
        mean = result.mean_distribution()
        assert sum(mean.values()) == pytest.approx(1.0)

    def test_predictor_failure_does_not_abort(self):
        from src.app.services.society.ensemble_runner import EnsembleRunner

        async def predictor(seed):
            if seed == 3:
                raise RuntimeError("simulated")
            return {s: 1 / len(STANCES) for s in STANCES}

        runner = EnsembleRunner(n_runs=5, concurrency=2)
        result = asyncio.run(runner.run(predictor))

        # 失敗は除外されるが残りは取得できる
        assert 0 < result.n <= 5
