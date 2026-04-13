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

import os
import re
from pathlib import Path
from typing import TypedDict

import logging
import yaml

from src.app.services.society.constants import STANCE_ORDER
from src.app.utils.distribution_metrics import (
    kl_divergence_symmetric,
    earth_movers_distance,
)

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


# 日本語政策用語の同義語テーブル
_SYNONYMS: dict[str, list[str]] = {
    "インフレ": ["物価上昇", "インフレーション"],
    "物価上昇": ["インフレ", "インフレーション"],
    "景気後退": ["リセッション", "不景気"],
    "リセッション": ["景気後退", "不景気"],
    "増税": ["税率引き上げ", "税負担増"],
    "税率引き上げ": ["増税", "税負担増"],
    "少子化": ["出生率低下", "人口減少"],
    "高齢化": ["超高齢社会", "老齢化"],
    "円安": ["通貨安", "為替下落"],
    "賃上げ": ["賃金上昇", "ベースアップ"],
}

_MIN_MATCH_THRESHOLD = 0.05


def _expand_synonyms(text: str) -> str:
    """テキスト中のキーワードを同義語で展開する。"""
    expanded = text
    for keyword, synonyms in _SYNONYMS.items():
        if keyword in text:
            expanded += " " + " ".join(synonyms)
    return expanded


def find_relevant_surveys(
    theme: str,
    surveys: list[SurveyRecord],
    top_k: int = 5,
    theme_category: str | None = None,
    exclude_survey_ids: list[str] | None = None,
) -> list[SurveyRecord]:
    """テーマキーワードでの関連調査検索。

    改善点:
    - theme_category によるプレフィルタ
    - 同義語展開
    - 最低マッチ閾値 (Jaccard >= 0.05)
    - exclude_survey_ids による leakage 防止（source で除外）
    """
    # カテゴリプレフィルタ
    candidates = surveys
    if theme_category is not None:
        candidates = [s for s in surveys if s.get("theme_category") == theme_category]

    # leakage 防止: exclude_survey_ids に含まれる source を除外
    if exclude_survey_ids:
        candidates = [s for s in candidates if s.get("source") not in exclude_survey_ids]

    # 同義語展開
    expanded_theme = _expand_synonyms(theme)
    theme_ngrams = _ngrams(expanded_theme)
    if not theme_ngrams:
        return []

    scored: list[tuple[float, SurveyRecord]] = []
    for survey in candidates:
        searchable = survey["theme"] + " " + " ".join(survey["relevance_keywords"])
        expanded_searchable = _expand_synonyms(searchable)
        score = _jaccard(theme_ngrams, _ngrams(expanded_searchable))
        if score >= _MIN_MATCH_THRESHOLD:
            scored.append((score, survey))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:top_k]]


def compare_with_surveys(
    simulation_distribution: dict[str, float],
    theme: str,
    data_dir: str,
    theme_category: str | None = None,
) -> ComparisonReport | None:
    """シミュレーション出力と調査データの比較レポートを生成する。

    theme_category を指定すると find_relevant_surveys のプレフィルタに使用される。
    """
    surveys = load_survey_data(data_dir)
    if not surveys:
        return None

    matched = find_relevant_surveys(theme, surveys, theme_category=theme_category)
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


def get_anchor_distribution(
    theme: str,
    theme_category: str,
    surveys: list[SurveyRecord],
) -> dict[str, float] | None:
    """テーマカテゴリに対応するアンカー分布を取得する。

    関連する調査のスタンス分布の加重平均を返す。
    マッチする調査がない場合は None を返す。

    Args:
        theme: シミュレーションのテーマ文
        theme_category: 推定済みのカテゴリ名
        surveys: 検索対象の SurveyRecord リスト
    """
    matched = find_relevant_surveys(theme, surveys, theme_category=theme_category)
    if not matched:
        return None

    avg: dict[str, float] = {k: 0.0 for k in STANCE_ORDER}
    n = len(matched)
    for survey in matched:
        for k in STANCE_ORDER:
            avg[k] += survey["stance_distribution"].get(k, 0.0)
    return {k: v / n for k, v in avg.items()}


def apply_survey_anchor(
    distribution: dict[str, float],
    anchor_distribution: dict[str, float] | None,
    alpha: float = 0.3,
) -> dict[str, float]:
    """シミュレーション分布をアンカー調査分布に向けてブレンドする。

    anchor_distribution が None の場合は distribution をそのまま返す（スキップ）。

    Args:
        distribution: シミュレーション出力の意見分布
        anchor_distribution: アンカーとなる調査の分布。None の場合はスキップ。
        alpha: アンカーの重み (0.0=変更なし, 1.0=完全にアンカーへ置換)

    Returns:
        ブレンド後の正規化済み分布。anchor_distribution=None の場合は元の分布。
    """
    if anchor_distribution is None:
        return distribution

    all_keys = set(distribution.keys()) | set(anchor_distribution.keys())
    blended = {
        k: (1.0 - alpha) * distribution.get(k, 0.0) + alpha * anchor_distribution.get(k, 0.0)
        for k in all_keys
    }
    total = sum(blended.values())
    if total <= 0:
        return distribution
    return {k: v / total for k, v in blended.items()}


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
