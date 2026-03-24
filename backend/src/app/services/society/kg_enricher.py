"""KG Enricher: ナレッジグラフのエンティティ・関係を使ってエージェントプロフィールを強化する"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def enrich_agents_from_kg(
    agents: list[dict],
    kg_entities: list[dict],
    kg_relations: list[dict],
    theme: str,
    max_context_per_agent: int = 3,
) -> list[dict]:
    """KG のエンティティ・関係を使ってエージェントプロフィールに kg_context を追加する。

    各エージェントの職業・地域・価値観とテーマに基づいて、関連する KG エンティティを
    マッチングし、その情報をコンテキストとして付与する。

    Args:
        agents: エージェントプロフィールのリスト
        kg_entities: KG のエンティティリスト
        kg_relations: KG の関係リスト
        theme: シミュレーションテーマ
        max_context_per_agent: エージェントあたりの最大コンテキスト数

    Returns:
        kg_context が追加されたエージェントリスト（in-place 更新）
    """
    if not kg_entities:
        logger.info("No KG entities available for enrichment")
        return agents

    # エンティティを importance 順にソート
    sorted_entities = sorted(
        kg_entities,
        key=lambda e: e.get("importance_score", 0.5),
        reverse=True,
    )

    # 関係をソース/ターゲット別にインデックス化
    relation_index: dict[str, list[dict]] = {}
    for r in kg_relations:
        src = r.get("source", "")
        tgt = r.get("target", "")
        relation_index.setdefault(src, []).append(r)
        relation_index.setdefault(tgt, []).append(r)

    # エンティティ型と職業/地域のマッピングキーワード
    type_relevance = {
        "market": ["会社員", "営業職", "経営者", "コンサルタント", "自営業"],
        "technology": ["エンジニア", "研究者", "デザイナー", "フリーランス"],
        "policy": ["公務員", "弁護士", "記者"],
        "resource": ["農業", "漁業", "建設作業員"],
        "person": [],  # 全員に関連
        "organization": ["会社員", "公務員"],
        "event": [],  # 全員に関連
    }

    enriched_count = 0

    for agent in agents:
        demographics = agent.get("demographics", {})
        occupation = demographics.get("occupation", "")
        region = demographics.get("region", "")
        values = agent.get("values", {})

        # エージェントに関連するエンティティを選出
        relevant_entities = _select_relevant_entities(
            sorted_entities, occupation, region, values,
            type_relevance, max_context_per_agent,
        )

        if not relevant_entities:
            continue

        # コンテキスト文字列を構築
        context_parts = []
        for entity in relevant_entities:
            name = entity.get("name", "")
            description = entity.get("description", "")
            entity_type = entity.get("type", "")

            # この entity に関連する関係を取得
            related = relation_index.get(name, [])[:2]
            relation_texts = []
            for rel in related:
                other = rel.get("target", "") if rel.get("source") == name else rel.get("source", "")
                rel_type = rel.get("type", "related")
                relation_texts.append(f"{other}と{rel_type}の関係")

            part = f"- {name}（{entity_type}）: {description}"
            if relation_texts:
                part += f"（{', '.join(relation_texts)}）"
            context_parts.append(part)

        if context_parts:
            agent["kg_context"] = (
                f"【関連する背景情報】\n"
                + "\n".join(context_parts)
            )
            enriched_count += 1

    logger.info(
        "KG enrichment: %d/%d agents enriched with context from %d entities",
        enriched_count, len(agents), len(kg_entities),
    )
    return agents


def _select_relevant_entities(
    entities: list[dict],
    occupation: str,
    region: str,
    values: dict,
    type_relevance: dict[str, list[str]],
    max_count: int,
) -> list[dict]:
    """エージェントプロフィールに関連するエンティティを選出する。"""
    scored: list[tuple[float, dict]] = []

    value_keywords = set(values.keys())

    for entity in entities:
        score = entity.get("importance_score", 0.5)
        entity_type = entity.get("type", "")
        entity_name = entity.get("name", "").lower()
        entity_desc = entity.get("description", "").lower()

        # 型の職業関連性ボーナス
        relevant_occupations = type_relevance.get(entity_type, [])
        if occupation in relevant_occupations:
            score += 0.2

        # 地域マッチボーナス
        if region and region.lower() in entity_desc:
            score += 0.15

        # 価値観マッチボーナス
        value_type_map = {
            "environment": ["環境", "climate", "carbon", "持続可能"],
            "growth": ["経済", "市場", "成長", "GDP"],
            "security": ["安全", "セキュリティ", "防衛"],
            "innovation": ["技術", "イノベーション", "AI", "DX"],
            "fairness": ["平等", "公平", "格差"],
        }
        for val_key in value_keywords:
            keywords = value_type_map.get(val_key, [])
            if any(kw in entity_name or kw in entity_desc for kw in keywords):
                score += 0.1
                break

        scored.append((score, entity))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entity for _, entity in scored[:max_count]]
