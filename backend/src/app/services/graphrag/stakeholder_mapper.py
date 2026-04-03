"""ステークホルダーマッパー: KnowledgeGraph → StakeholderSeed リスト"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.app.services.graphrag.pipeline import KnowledgeGraph

logger = logging.getLogger(__name__)

SOURCE_ENTITY_ID_FIELD = "source_entity_id"
MIN_STAKEHOLDER_COUNT = 5

STAKEHOLDER_TYPES = frozenset({
    "PERSON", "GROUP", "ORG", "ORGANIZATION", "STAKEHOLDER",
})


@dataclass
class StakeholderSeed:
    entity_id: str
    name: str
    entity_type: str
    goals_hint: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    community: str = ""
    description: str = ""


def map_stakeholders(
    kg: KnowledgeGraph,
    max_count: int = 15,
) -> list[StakeholderSeed]:
    """KnowledgeGraph から StakeholderSeed リストを生成する。

    - degree_centrality: kg.relations の source/target 名で集計（entity.importance_score は常に 0.5 のため不使用）
    - community_label=None は "_none" に正規化
    - コミュニティ多様性: 1 コミュニティあたり最高次数 1 件を先に選出し、残りを次数順で補充
    - 同一次数のタイブレーカーは名前昇順（決定論的）
    - description は 500 文字に切り詰め
    - 返却件数は max_count 上限（min_count チェックは呼び出し元が行う）
    """
    # 次数計算（relation の source/target はエンティティ名）
    degree: Counter[str] = Counter()
    for rel in kg.relations:
        if rel.get("source"):
            degree[rel["source"]] += 1
        if rel.get("target"):
            degree[rel["target"]] += 1

    # ステークホルダー候補をフィルタリング
    candidates = []
    for e in kg.entities:
        if e.get("type", "").upper() not in STAKEHOLDER_TYPES:
            continue
        community = e.get("community_label") or "_none"
        candidates.append({
            "id": e["id"],
            "name": e["name"],
            "type": e.get("type", ""),
            "description": (e.get("description") or "")[:500],
            "community": community,
            "degree": degree[e["name"]],
        })

    if not candidates:
        return []

    def _sort_key(c: dict) -> tuple:
        return (-c["degree"], c["name"])

    # コミュニティごとにバケット分け
    buckets: dict[str, list[dict]] = {}
    for c in candidates:
        buckets.setdefault(c["community"], []).append(c)

    # 各バケットから最高次数 1 件を先に選出
    selected = []
    remainder = []
    for bucket in buckets.values():
        sorted_bucket = sorted(bucket, key=_sort_key)
        selected.append(sorted_bucket[0])
        remainder.extend(sorted_bucket[1:])

    # 残りを次数降順・名前昇順で補充
    remainder.sort(key=_sort_key)
    combined = (selected + remainder)[:max_count]

    logger.debug("map_stakeholders: %d candidates → %d seeds", len(candidates), len(combined))

    return [
        StakeholderSeed(
            entity_id=c["id"],
            name=c["name"],
            entity_type=c["type"],
            goals_hint=[],
            relationships=[],
            community=c["community"],
            description=c["description"],
        )
        for c in combined
    ]
