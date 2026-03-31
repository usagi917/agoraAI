"""実世界データグラウンディングモジュール

エージェントの推論を実世界のファクトに基づかせるためのサービス。

- load_grounding_facts  : config/grounding/*.yaml からファクトを読み込み、
                          テーマとのキーワードマッチングでフィルタリング・ソート
- distribute_facts_to_agents : エージェントの属性に基づき関連度の高いファクトを配布
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict

import yaml

logger = logging.getLogger(__name__)

# プロジェクトルートから config/grounding/ への相対パス
_DEFAULT_GROUNDING_DIR = Path(__file__).parents[5] / "config" / "grounding"


class GroundingFact(TypedDict):
    """グラウンディングファクトの型定義."""

    fact: str
    source: str
    date: str
    category: str
    relevance_keywords: list[str]


# ---------------------------------------------------------------------------
# Keyword tokenization
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """テキストをスペース区切りでトークン化する."""
    return [t.strip() for t in text.split() if t.strip()]


# ---------------------------------------------------------------------------
# load_grounding_facts
# ---------------------------------------------------------------------------

def load_grounding_facts(
    theme: str,
    grounding_dir: str | Path | None = None,
) -> list[GroundingFact]:
    """テーマに関連するグラウンディングファクトを返す.

    grounding_dir 内の全 *.yaml ファイルを読み込み、
    各ファクトの relevance_keywords とテーマのキーワードのマッチングスコアを算出。
    スコア > 0 のファクトをスコア降順で最大10件返す。

    Args:
        theme: 検索テーマ（スペース区切りで複数キーワード可）
        grounding_dir: YAML ファイルのディレクトリ。None の場合デフォルトパスを使用。

    Returns:
        マッチしたファクトのリスト（スコア降順、最大10件）
    """
    if not theme or not theme.strip():
        return []

    dir_path = Path(grounding_dir) if grounding_dir is not None else _DEFAULT_GROUNDING_DIR

    if not dir_path.exists() or not dir_path.is_dir():
        return []

    theme_keywords = _tokenize(theme)
    if not theme_keywords:
        return []

    all_facts: list[GroundingFact] = []

    for yaml_file in sorted(dir_path.glob("*.yaml")):
        try:
            content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except Exception as exc:
            logger.warning("Failed to load %s: %s", yaml_file, exc)
            continue

        if not isinstance(data, dict) or "facts" not in data:
            continue

        facts = data["facts"]
        if not isinstance(facts, list):
            continue

        for raw in facts:
            if not isinstance(raw, dict):
                continue
            # 必須フィールドの存在確認
            fact_text = raw.get("fact", "")
            source = raw.get("source", "")
            date = raw.get("date", "")
            if not fact_text or not source or not date:
                continue
            fact: GroundingFact = {
                "fact": fact_text,
                "source": source,
                "date": str(date),
                "category": raw.get("category", ""),
                "relevance_keywords": raw.get("relevance_keywords", []),
            }
            all_facts.append(fact)

    # スコアリング: 双方向マッチング
    # 1) テーマトークンがファクトキーワードに一致 (完全一致)
    # 2) ファクトキーワードがテーマ全文に出現 (部分文字列一致)
    # スコア = マッチしたファクトキーワード数 / ファクトキーワード総数
    theme_lower = theme.lower()
    theme_kw_set = set(theme_keywords)
    scored: list[tuple[float, GroundingFact]] = []
    for fact in all_facts:
        fact_keywords = fact["relevance_keywords"]
        if not fact_keywords:
            continue
        matched = 0
        for kw in fact_keywords:
            if kw in theme_kw_set or kw in theme_lower:
                matched += 1
        if matched > 0:
            score = matched / len(fact_keywords)
            scored.append((score, fact))

    # スコア降順ソート
    scored.sort(key=lambda x: x[0], reverse=True)

    return [fact for _, fact in scored[:10]]


# ---------------------------------------------------------------------------
# distribute_facts_to_agents
# ---------------------------------------------------------------------------

# エージェントの職業カテゴリと関連するファクトカテゴリ・キーワードのマッピング
_OCCUPATION_RELEVANCE: dict[str, list[str]] = {
    "農業従事者": ["agriculture", "農業", "農家", "農村", "食料"],
    "農家": ["agriculture", "農業", "農家", "農村", "食料"],
    "会社員": ["economy", "賃金", "雇用", "労働"],
    "会社員（管理職）": ["economy", "賃金", "雇用", "労働"],
    "公務員": ["economy", "行政", "雇用"],
    "教員": ["education", "子育て", "少子化"],
    "医療従事者": ["healthcare", "医療", "少子化"],
    "自営業": ["economy", "農業", "雇用"],
    "無職": ["economy", "失業", "雇用"],
    "学生": ["education", "人口", "少子化"],
}

# 所得層と関連カテゴリのマッピング
_INCOME_RELEVANCE: dict[str, list[str]] = {
    "低所得層": ["economy", "賃金", "失業"],
    "中間層": ["economy"],
    "高所得層": ["economy"],
}


def _compute_agent_fact_score(agent: dict, fact: GroundingFact) -> float:
    """エージェントとファクトの関連度スコアを算出する.

    Args:
        agent: エージェント情報（demographics を含む）
        fact: グラウンディングファクト

    Returns:
        関連度スコア（0.0 以上）
    """
    score = 0.0
    demographics = agent.get("demographics", {})
    occupation = demographics.get("occupation", "")
    income_bracket = demographics.get("income_bracket", "")

    fact_category = fact.get("category", "")
    fact_keywords = set(fact.get("relevance_keywords", []))

    # 職業との関連度
    occupation_signals = _OCCUPATION_RELEVANCE.get(occupation, [])
    for signal in occupation_signals:
        if signal == fact_category or signal in fact_keywords:
            score += 1.0

    # 職業名そのものがキーワードに含まれる場合はボーナス
    if occupation and occupation in fact_keywords:
        score += 2.0

    # 所得層との関連度
    income_signals = _INCOME_RELEVANCE.get(income_bracket, [])
    for signal in income_signals:
        if signal == fact_category or signal in fact_keywords:
            score += 0.5

    return score


def distribute_facts_to_agents(
    agents: list[dict],
    facts: list[GroundingFact],
    max_per_agent: int = 5,
) -> dict[int, list[GroundingFact]]:
    """エージェントの属性に基づきファクトを配布する.

    各エージェントの demographics (occupation, region, income_bracket) と
    各ファクトの category/keywords のマッチングで関連度スコアを算出し、
    関連度上位 max_per_agent 件を各エージェントに配布する。

    Args:
        agents: エージェントのリスト（各要素は demographics を持つ dict）
        facts: 配布するファクトのリスト
        max_per_agent: 1エージェントあたりの最大配布件数

    Returns:
        エージェントインデックス → 配布ファクトリスト の dict
    """
    if not agents:
        return {}

    result: dict[int, list[GroundingFact]] = {}

    for idx, agent in enumerate(agents):
        if not facts:
            result[idx] = []
            continue

        # 各ファクトの関連度スコアを計算
        scored: list[tuple[float, GroundingFact]] = []
        for fact in facts:
            score = _compute_agent_fact_score(agent, fact)
            scored.append((score, fact))

        # スコア降順ソート（同スコアの場合はファクトの元の順序を維持）
        scored.sort(key=lambda x: x[0], reverse=True)

        # 上位 max_per_agent 件を取得
        top_facts = [fact for _, fact in scored[:max_per_agent]]
        result[idx] = top_facts

    return result
