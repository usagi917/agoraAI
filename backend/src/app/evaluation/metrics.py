"""具象メトリクス: 既存 evaluation.py のロジックを BaseMetric パターンに昇格"""

import math
from collections import Counter
from typing import Any

from src.app.evaluation.base import BaseMetric


def _jsd(p: dict[str, float], q: dict[str, float]) -> float:
    """Jensen-Shannon Divergence (自然対数ベース) を計算する.

    Args:
        p: 予測分布 (カテゴリ → 確率)
        q: 観測分布 (カテゴリ → 確率)

    Returns:
        JSD 値 (0 ≤ JSD ≤ ln(2))
    """
    all_keys = set(p) | set(q)
    if not all_keys:
        return 0.0

    m = {k: 0.5 * (p.get(k, 0.0) + q.get(k, 0.0)) for k in all_keys}

    def _kl(dist: dict[str, float], ref: dict[str, float]) -> float:
        kl = 0.0
        for k in all_keys:
            pk = dist.get(k, 0.0)
            mk = ref.get(k, 0.0)
            if pk > 0 and mk > 0:
                kl += pk * math.log(pk / mk)
        return kl

    return 0.5 * _kl(p, m) + 0.5 * _kl(q, m)

# 標準スタンスカテゴリ
STANDARD_STANCES = {"賛成", "反対", "中立", "条件付き賛成", "条件付き反対"}


class DiversityMetric(BaseMetric):
    """Shannon entropy ベースの意見多様性指標 (0-1 正規化)。"""

    name = "diversity"
    description = "スタンス分布の均等性 (Shannon entropy)"

    def compute(self, **kwargs: Any) -> dict:
        responses = kwargs.get("responses", [])
        if not responses:
            return {"score": 0.0, "details": {"method": "shannon_entropy_normalized"}}

        stances = [r.get("stance", "中立") for r in responses]
        counter = Counter(stances)
        total = len(stances)
        n_categories = len(counter)

        if n_categories <= 1:
            return {"score": 0.0, "details": {"method": "shannon_entropy_normalized", "n_categories": 1}}

        entropy = 0.0
        for count in counter.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)

        max_entropy = math.log2(n_categories)
        score = round(entropy / max_entropy, 4) if max_entropy > 0 else 0.0

        return {
            "score": score,
            "details": {
                "method": "shannon_entropy_normalized",
                "n_categories": n_categories,
                "entropy": round(entropy, 4),
            },
        }


class ConsistencyMetric(BaseMetric):
    """プロフィールと回答の整合性スコア (0-1)。"""

    name = "consistency"
    description = "エージェントの性格特性と回答の一貫性"

    def compute(self, **kwargs: Any) -> dict:
        agents = kwargs.get("agents", [])
        responses = kwargs.get("responses", [])

        if not agents or not responses or len(agents) != len(responses):
            return {"score": 0.0, "details": {"method": "profile_response_alignment"}}

        consistent_count = 0
        total = len(agents)

        for agent, resp in zip(agents, responses):
            big_five = agent.get("big_five", {})
            values = agent.get("values", {})
            stance = resp.get("stance", "中立")

            score = 0.0
            checks = 0

            if big_five.get("O", 0.5) > 0.7:
                if stance in ("賛成", "条件付き賛成"):
                    score += 1.0
                elif stance == "中立":
                    score += 0.5
                checks += 1
            elif big_five.get("O", 0.5) < 0.3:
                if stance in ("反対", "条件付き反対"):
                    score += 1.0
                elif stance == "中立":
                    score += 0.5
                checks += 1

            if big_five.get("N", 0.5) > 0.7:
                if resp.get("confidence", 0.5) < 0.6:
                    score += 1.0
                checks += 1

            if values:
                top_value = max(values, key=values.get) if values else ""
                reason = resp.get("reason", "").lower()
                if top_value and top_value in reason:
                    score += 1.0
                checks += 1

            if checks > 0 and score / checks >= 0.5:
                consistent_count += 1

        final_score = round(consistent_count / total, 4) if total > 0 else 0.0
        return {
            "score": final_score,
            "details": {
                "method": "profile_response_alignment",
                "consistent_count": consistent_count,
                "total": total,
            },
        }


class ConvergenceMetric(BaseMetric):
    """多数派への収束度 (0-1)。高いほど意見が集約している。"""

    name = "convergence"
    description = "多数派スタンスへの集中度"

    def compute(self, **kwargs: Any) -> dict:
        responses = kwargs.get("responses", [])
        if not responses:
            return {"score": 0.0, "details": {"method": "majority_ratio"}}

        stances = [r.get("stance", "中立") for r in responses]
        counter = Counter(stances)
        total = len(stances)
        majority_count = counter.most_common(1)[0][1]
        majority_stance = counter.most_common(1)[0][0]

        score = round(majority_count / total, 4)
        return {
            "score": score,
            "details": {
                "method": "majority_ratio",
                "majority_stance": majority_stance,
                "majority_count": majority_count,
                "total": total,
            },
        }


class CoverageMetric(BaseMetric):
    """スタンスカバレッジ (0-1)。標準5カテゴリのうち何割が出現したか。"""

    name = "coverage"
    description = "標準スタンスカテゴリのカバー率"

    def compute(self, **kwargs: Any) -> dict:
        responses = kwargs.get("responses", [])
        if not responses:
            return {"score": 0.0, "details": {"method": "stance_coverage"}}

        observed = {r.get("stance", "中立") for r in responses}
        covered = observed & STANDARD_STANCES
        score = round(len(covered) / len(STANDARD_STANCES), 4)

        return {
            "score": score,
            "details": {
                "method": "stance_coverage",
                "observed_stances": sorted(observed),
                "covered_count": len(covered),
                "total_categories": len(STANDARD_STANCES),
            },
        }


class JSDMetric(BaseMetric):
    """Jensen-Shannon Divergence: 予測分布と観測分布の乖離度 (主指標)."""

    name = "jsd"
    description = "予測分布と観測分布の Jensen-Shannon Divergence"

    def compute(self, **kwargs: Any) -> dict:
        predicted: dict[str, float] = kwargs.get("predicted", {})
        observed: dict[str, float] = kwargs.get("observed", {})

        if not predicted and not observed:
            return {"score": 0.0, "details": {"method": "jensen_shannon_divergence"}}

        score = _jsd(predicted, observed)
        return {
            "score": round(score, 8),
            "details": {
                "method": "jensen_shannon_divergence",
                "predicted_categories": len(predicted),
                "observed_categories": len(observed),
            },
        }


class SubgroupAccuracyMetric(BaseMetric):
    """サブグループ別 JSD: 過少代表グループの精度低下を検出する（読み取り専用）."""

    name = "subgroup_accuracy"
    description = "サブグループ別の Jensen-Shannon Divergence"

    def compute(self, **kwargs: Any) -> dict:
        predicted_by_group: dict[str, dict[str, float]] = kwargs.get("predicted_by_group", {})
        observed_by_group: dict[str, dict[str, float]] = kwargs.get("observed_by_group", {})

        if not predicted_by_group or not observed_by_group:
            return {"score": 0.0, "details": {"method": "subgroup_jsd", "subgroup_scores": {}}}

        subgroup_scores: dict[str, float] = {}
        for group in predicted_by_group:
            if group in observed_by_group:
                subgroup_scores[group] = round(
                    _jsd(predicted_by_group[group], observed_by_group[group]), 8
                )

        avg_score = sum(subgroup_scores.values()) / len(subgroup_scores) if subgroup_scores else 0.0
        worst = max(subgroup_scores, key=subgroup_scores.get) if subgroup_scores else ""

        return {
            "score": round(avg_score, 8),
            "details": {
                "method": "subgroup_jsd",
                "subgroup_scores": subgroup_scores,
                "worst_subgroup": worst,
            },
        }
