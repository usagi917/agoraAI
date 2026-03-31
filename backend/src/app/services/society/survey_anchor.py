"""世論調査アンカリングモジュール

シミュレーション出力と実世論調査の分布乖離を定量測定する。

- load_survey_data       : YAMLからの調査データ読み込み
- find_relevant_surveys  : テーマキーワードでの関連調査検索
- kl_divergence_symmetric: 対称KL-divergence
- earth_movers_distance  : 序数距離を考慮したEMD
- compare_with_surveys   : シミュレーション出力と調査データの比較レポート
- map_to_five_stances    : 回答選択肢→5段階スタンスへの変換
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import TypedDict

import logging
import yaml

from src.app.services.society.constants import STANCE_ORDER

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = [
    "theme", "question", "source", "survey_date",
    "sample_size", "method", "stance_distribution",
    "theme_category", "relevance_keywords",
]


class SurveyRecord(TypedDict):
    theme: str
    question: str
    source: str
    survey_date: str
    sample_size: int
    method: str
    stance_distribution: dict[str, float]
    theme_category: str
    relevance_keywords: list[str]


class ComparisonReport(TypedDict):
    theme: str
    matched_surveys: list[SurveyRecord]
    kl_divergence: float
    emd: float
    per_survey_deviations: list[dict]
    best_match_source: str


def _validate_survey_record(record: dict) -> SurveyRecord:
    for field in REQUIRED_FIELDS:
        if field not in record or record[field] is None:
            raise ValueError(f"Missing required field: {field}")

    dist = record["stance_distribution"]
    expected_keys = set(STANCE_ORDER)

    invalid_keys = set(dist.keys()) - expected_keys
    if invalid_keys:
        raise ValueError(
            f"Unknown stance keys: {invalid_keys}. Expected: {STANCE_ORDER}"
        )

    missing_keys = expected_keys - set(dist.keys())
    if missing_keys:
        raise ValueError(
            f"Missing stance keys: {sorted(missing_keys)}. Expected all: {STANCE_ORDER}"
        )

    total = sum(dist.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(
            f"stance_distribution must sum to 1.0 (±0.01), got {total:.4f}"
        )

    return SurveyRecord(
        theme=str(record["theme"]),
        question=str(record["question"]),
        source=str(record["source"]),
        survey_date=str(record["survey_date"]),
        sample_size=int(record["sample_size"]),
        method=str(record["method"]),
        stance_distribution=dict(dist),
        theme_category=str(record["theme_category"]),
        relevance_keywords=list(record["relevance_keywords"]),
    )


def load_survey_data(data_dir: str) -> list[SurveyRecord]:
    """ディレクトリからYAMLファイルを再帰的に読み込み、バリデーション済みのSurveyRecordリストを返す。"""
    records: list[SurveyRecord] = []
    data_path = Path(data_dir)

    for yaml_file in sorted(data_path.rglob("*.yaml")):
        if yaml_file.name == "schema.yaml":
            continue
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            logger.warning("YAML parse error in %s: %s", yaml_file, exc)
            continue
        if not data or "surveys" not in data:
            logger.warning("Skipping %s: missing 'surveys' key", yaml_file)
            continue
        for entry in data["surveys"]:
            records.append(_validate_survey_record(entry))

    return records


def _normalize_compact(value: str) -> str:
    text = value.lower().strip()
    return re.sub(r"[\s、。・,./!！?？:：;；()\[\]{}「」『』【】\-_=+]+", "", text)


def _ngrams(value: str, size: int = 2) -> set[str]:
    compact = _normalize_compact(value)
    if not compact:
        return set()
    if len(compact) <= size:
        return {compact}
    return {compact[i:i + size] for i in range(len(compact) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def find_relevant_surveys(
    theme: str,
    surveys: list[SurveyRecord],
    top_k: int = 5,
) -> list[SurveyRecord]:
    """テーマキーワードでの関連調査検索。n-gram Jaccard によるマッチング。"""
    theme_ngrams = _ngrams(theme)
    if not theme_ngrams:
        return []

    scored: list[tuple[float, SurveyRecord]] = []
    for survey in surveys:
        # テーマ名とキーワードを結合してマッチング
        searchable = survey["theme"] + " " + " ".join(survey["relevance_keywords"])
        score = _jaccard(theme_ngrams, _ngrams(searchable))
        if score > 0:
            scored.append((score, survey))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:top_k]]


def kl_divergence_symmetric(
    p: dict[str, float],
    q: dict[str, float],
    smoothing: float = 1e-6,
) -> float:
    """対称KL-divergence: (KL(p||q) + KL(q||p)) / 2。スムージング付き。"""
    all_keys = set(p.keys()) | set(q.keys())

    # スムージング適用
    p_smooth = {k: p.get(k, 0.0) + smoothing for k in all_keys}
    q_smooth = {k: q.get(k, 0.0) + smoothing for k in all_keys}

    # 再正規化
    p_total = sum(p_smooth.values())
    q_total = sum(q_smooth.values())
    p_norm = {k: v / p_total for k, v in p_smooth.items()}
    q_norm = {k: v / q_total for k, v in q_smooth.items()}

    kl_pq = sum(p_norm[k] * math.log(p_norm[k] / q_norm[k]) for k in all_keys)
    kl_qp = sum(q_norm[k] * math.log(q_norm[k] / p_norm[k]) for k in all_keys)

    return (kl_pq + kl_qp) / 2.0


def earth_movers_distance(
    p: dict[str, float],
    q: dict[str, float],
) -> float:
    """序数距離を考慮したEarth Mover's Distance。

    スタンスの序数: 賛成=0, 条件付き賛成=1, 中立=2, 条件付き反対=3, 反対=4
    累積差分の絶対値の合計。
    """
    p_vals = [p.get(s, 0.0) for s in STANCE_ORDER]
    q_vals = [q.get(s, 0.0) for s in STANCE_ORDER]

    emd = 0.0
    cumulative = 0.0
    for i in range(len(STANCE_ORDER)):
        cumulative += p_vals[i] - q_vals[i]
        emd += abs(cumulative)

    return emd


def compare_with_surveys(
    simulation_distribution: dict[str, float],
    theme: str,
    data_dir: str,
) -> ComparisonReport | None:
    """シミュレーション出力と調査データの比較レポートを生成する。"""
    surveys = load_survey_data(data_dir)
    if not surveys:
        return None

    matched = find_relevant_surveys(theme, surveys)
    if not matched:
        return None

    per_survey_deviations: list[dict] = []
    total_kl = 0.0
    total_emd = 0.0

    for survey in matched:
        kl = kl_divergence_symmetric(simulation_distribution, survey["stance_distribution"])
        emd = earth_movers_distance(simulation_distribution, survey["stance_distribution"])
        per_survey_deviations.append({
            "source": survey["source"],
            "theme": survey["theme"],
            "kl_divergence": kl,
            "emd": emd,
        })
        total_kl += kl
        total_emd += emd

    n = len(matched)
    avg_kl = total_kl / n
    avg_emd = total_emd / n

    best = min(per_survey_deviations, key=lambda x: x["kl_divergence"])

    return ComparisonReport(
        theme=theme,
        matched_surveys=matched,
        kl_divergence=avg_kl,
        emd=avg_emd,
        per_survey_deviations=per_survey_deviations,
        best_match_source=best["source"],
    )


def map_to_five_stances(
    original: dict[str, float],
    mapping_type: str,
) -> dict[str, float]:
    """回答選択肢を5段階スタンスにマップする。

    mapping_type:
      "binary"   : 賛成/反対の2択 → 5段階
      "likert_5" : 5段階リッカート → 5段階スタンス
    """
    result = {s: 0.0 for s in STANCE_ORDER}

    if mapping_type == "binary":
        agree = original.get("賛成", 0.0)
        disagree = original.get("反対", 0.0)
        total = agree + disagree
        if total == 0:
            return {s: 0.2 for s in STANCE_ORDER}
        # 2択を5段階に分散
        result["賛成"] = agree * 0.6
        result["条件付き賛成"] = agree * 0.4
        result["中立"] = 0.0
        result["条件付き反対"] = disagree * 0.4
        result["反対"] = disagree * 0.6

    elif mapping_type == "likert_5":
        likert_map = {
            "非常にそう思う": "賛成",
            "そう思う": "条件付き賛成",
            "どちらとも": "中立",
            "そう思わない": "条件付き反対",
            "全くそう思わない": "反対",
        }
        for label, value in original.items():
            stance = likert_map.get(label)
            if stance:
                result[stance] = value

    else:
        raise ValueError(f"Unknown mapping_type: {mapping_type!r}. Expected 'binary' or 'likert_5'.")

    # 再正規化
    total = sum(result.values())
    if total > 0:
        result = {k: v / total for k, v in result.items()}

    return result
