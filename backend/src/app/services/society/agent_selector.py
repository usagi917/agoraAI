"""エージェント選抜エンジン: テーマに基づいて住民を選抜する"""

import logging
import random
from typing import Any

logger = logging.getLogger(__name__)

# テーマ→関連トピックのマッピング
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "economy": ["経済", "金融", "株", "投資", "景気", "雇用", "賃金", "物価", "GDP", "budget"],
    "technology": ["技術", "AI", "ロボット", "デジタル", "IT", "DX", "自動化", "IoT", "5G"],
    "environment": ["環境", "気候", "温暖化", "エネルギー", "再生可能", "脱炭素", "CO2", "自然"],
    "health": ["健康", "医療", "病院", "ワクチン", "感染", "介護", "福祉", "保険"],
    "education": ["教育", "学校", "大学", "学習", "研究", "奨学金", "入試", "リカレント"],
    "security": ["安全", "防衛", "軍事", "テロ", "犯罪", "警察", "サイバー"],
    "immigration": ["移民", "外国人", "多文化", "在留", "難民", "共生"],
    "taxation": ["税", "消費税", "所得税", "控除", "財政", "予算"],
    "welfare": ["福祉", "年金", "生活保護", "子育て", "少子化", "高齢化"],
    "energy": ["エネルギー", "原発", "太陽光", "風力", "電力", "蓄電"],
}


def _extract_relevant_topics(theme: str) -> list[str]:
    """テーマテキストから関連トピックを抽出する。"""
    theme_lower = theme.lower()
    relevant = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in theme_lower:
                relevant.append(topic)
                break

    # トピックが見つからない場合、全トピックを対象にする
    if not relevant:
        relevant = list(TOPIC_KEYWORDS.keys())

    return relevant


def _score_agent(agent: dict, relevant_topics: list[str]) -> float:
    """エージェントのテーマ関連スコアを計算する (0-1)。"""
    shock = agent.get("shock_sensitivity", {})
    if not shock or not relevant_topics:
        return 0.5

    scores = [shock.get(t, 0.3) for t in relevant_topics]
    return sum(scores) / len(scores) if scores else 0.5


def _stratified_sample(
    agents: list[dict],
    scores: list[float],
    target_count: int,
) -> list[int]:
    """スコアに基づく層化抽出。多様性保証のため各層から均等にサンプリングする。"""
    n = len(agents)
    if n <= target_count:
        return list(range(n))

    # 4層に分割
    indexed_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    quartile_size = n // 4
    strata = [
        [idx for idx, _ in indexed_scores[:quartile_size]],           # top 25%
        [idx for idx, _ in indexed_scores[quartile_size:2*quartile_size]],
        [idx for idx, _ in indexed_scores[2*quartile_size:3*quartile_size]],
        [idx for idx, _ in indexed_scores[3*quartile_size:]],         # bottom 25%
    ]

    # 上位層から多め、下位層から少なめにサンプリング
    layer_ratios = [0.40, 0.30, 0.20, 0.10]
    selected: list[int] = []

    for stratum, ratio in zip(strata, layer_ratios):
        sample_size = max(1, int(target_count * ratio))
        sample_size = min(sample_size, len(stratum))
        selected.extend(random.sample(stratum, sample_size))

    # 不足分を上位層から追加
    remaining = target_count - len(selected)
    if remaining > 0:
        all_remaining = [i for i in range(n) if i not in set(selected)]
        all_remaining.sort(key=lambda i: scores[i], reverse=True)
        selected.extend(all_remaining[:remaining])

    return selected[:target_count]


def _ensure_diversity(
    agents: list[dict],
    selected_indices: list[int],
) -> list[int]:
    """選抜結果の多様性を検証し、不足属性があれば補充する。"""
    selected_set = set(selected_indices)

    # 地域の多様性チェック
    selected_regions = {agents[i].get("demographics", {}).get("region", "") for i in selected_indices}
    all_regions = {a.get("demographics", {}).get("region", "") for a in agents}
    missing_regions = all_regions - selected_regions

    for region in missing_regions:
        # 該当地域から1人追加
        for i, a in enumerate(agents):
            if i not in selected_set and a.get("demographics", {}).get("region") == region:
                selected_indices.append(i)
                selected_set.add(i)
                break

    return selected_indices


async def select_agents(
    agents: list[dict],
    theme: str,
    target_count: int = 100,
    min_count: int = 50,
    max_count: int = 200,
) -> list[dict]:
    """テーマに基づいてエージェントを選抜する。

    Returns:
        選抜されたエージェントプロフィールのリスト
    """
    target_count = max(min_count, min(max_count, target_count))
    target_count = min(target_count, len(agents))

    # テーマから関連トピックを抽出
    relevant_topics = _extract_relevant_topics(theme)
    logger.info("Theme topics: %s", relevant_topics)

    # スコアリング
    scores = [_score_agent(a, relevant_topics) for a in agents]

    # 層化抽出
    selected_indices = _stratified_sample(agents, scores, target_count)

    # 多様性保証
    selected_indices = _ensure_diversity(agents, selected_indices)

    # 重複除去
    seen = set()
    unique_indices = []
    for idx in selected_indices:
        if idx not in seen:
            seen.add(idx)
            unique_indices.append(idx)

    selected = [agents[i] for i in unique_indices]
    logger.info(
        "Selected %d agents from %d (theme: %s, topics: %s)",
        len(selected), len(agents), theme[:50], relevant_topics,
    )
    return selected
