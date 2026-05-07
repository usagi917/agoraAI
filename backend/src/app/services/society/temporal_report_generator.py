"""Phase 10: 時系列統合レポート生成器.

TimeAxisOrchestrator の snapshots と (任意の) Ensemble CI を受け取って、
各 horizon の駆動要因 / 長期 shift / what-if 比較を含む dict を返す。
ナラティブ生成は呼び出し側で別 LLM コール (narrative_generator) と組み合わせる前提。
"""

from __future__ import annotations

from typing import Any

from src.app.services.society.time_axis_orchestrator import TimeStepSnapshot

CredibleIntervalsPerStep = dict[str, dict[str, dict[str, dict[str, float]]]]
"""key (t0..t5) -> level (50/80/95) -> stance -> {lower, median, upper}"""


class TemporalReportGenerator:
    def __init__(self, top_factors: int = 3) -> None:
        self.top_factors = top_factors

    def generate(
        self,
        snapshots: list[TimeStepSnapshot],
        theme: str = "",
        ci_per_step: CredibleIntervalsPerStep | None = None,
        alternative_snapshots: list[TimeStepSnapshot] | None = None,
        narrative_per_step: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        timeline: list[dict[str, Any]] = []
        prev_distribution: dict[str, float] | None = None

        for snap in snapshots:
            distribution = dict(snap.distribution)
            driving = self._driving_factors(prev_distribution, distribution)
            entry: dict[str, Any] = {
                "key": snap.step.key,
                "label": snap.step.label,
                "delta_days": snap.step.delta_days,
                "t_index": snap.step.t_index,
                "distribution": distribution,
                "driving_factors": driving,
            }
            if snap.market_prices is not None:
                entry["market_prices"] = list(snap.market_prices)
            if ci_per_step is not None and snap.step.key in ci_per_step:
                entry["credible_intervals"] = ci_per_step[snap.step.key]
            if narrative_per_step is not None and snap.step.key in narrative_per_step:
                entry["narrative"] = narrative_per_step[snap.step.key]
            if snap.metadata is not None:
                entry["metadata"] = snap.metadata
            timeline.append(entry)
            prev_distribution = distribution

        report: dict[str, Any] = {
            "theme": theme,
            "timeline": timeline,
            "summary": self._summary(snapshots),
        }

        if alternative_snapshots is not None:
            report["what_if"] = self._build_what_if(snapshots, alternative_snapshots)

        return report

    def _driving_factors(
        self,
        prev: dict[str, float] | None,
        current: dict[str, float],
    ) -> list[dict[str, Any]]:
        if prev is None:
            return []
        deltas = []
        for stance in current.keys() | prev.keys():
            delta = current.get(stance, 0.0) - prev.get(stance, 0.0)
            if abs(delta) < 1e-9:
                continue
            deltas.append({"stance": stance, "delta": delta})
        deltas.sort(key=lambda d: abs(d["delta"]), reverse=True)
        return deltas[: self.top_factors]

    def _summary(self, snapshots: list[TimeStepSnapshot]) -> dict[str, Any]:
        if not snapshots:
            return {"long_term_shift": {}, "horizons": 0}
        first = snapshots[0].distribution
        last = snapshots[-1].distribution
        shift: dict[str, float] = {}
        for stance in first.keys() | last.keys():
            shift[stance] = last.get(stance, 0.0) - first.get(stance, 0.0)
        return {
            "long_term_shift": shift,
            "horizons": len(snapshots),
            "from": snapshots[0].step.key,
            "to": snapshots[-1].step.key,
        }

    def _build_what_if(
        self,
        baseline: list[TimeStepSnapshot],
        alternative: list[TimeStepSnapshot],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        n = min(len(baseline), len(alternative))
        for i in range(n):
            b = baseline[i].distribution
            a = alternative[i].distribution
            delta: dict[str, float] = {}
            for stance in a.keys() | b.keys():
                delta[stance] = a.get(stance, 0.0) - b.get(stance, 0.0)
            result.append({
                "key": baseline[i].step.key,
                "delta": delta,
                "baseline": dict(b),
                "alternative": dict(a),
            })
        return result
