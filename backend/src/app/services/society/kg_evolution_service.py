"""KG Evolution Service: KG更新をGraphDiff形式に変換しSSEでリアルタイム配信する"""

import logging
import re

from src.app.services.society.kg_updater import extract_kg_updates_from_round
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


def _sanitize_id(name: str) -> str:
    """エンティティ名をID用にサニタイズする。"""
    return re.sub(r"[^a-zA-Z0-9\u3000-\u9fff\uff00-\uffef-]", "_", name.strip())


# KGエンティティのtype → GraphNodeのtype マッピング
_KG_TYPE_MAP: dict[str, str] = {
    "concept": "concept",
    "risk": "risk",
    "opportunity": "opportunity",
    "stakeholder": "organization",
    "metric": "metric",
    "person": "person",
    "organization": "organization",
    "policy": "policy",
    "market": "market",
    "technology": "technology",
    "resource": "resource",
    "event": "event",
}

# KG関係のtype → GraphEdgeのrelation_type マッピング
_KG_RELATION_MAP: dict[str, str] = {
    "影響": "influence",
    "対立": "conflict",
    "依存": "trust",
    "協力": "trust",
    "規制": "influence",
    "競合": "conflict",
    "支援": "trust",
    "供給": "trust",
    "所有": "trust",
    "同盟": "trust",
}


class KGEvolutionService:
    """シミュレーション中のKG進化をSSEでリアルタイム配信するサービス。

    既存の kg_updater.extract_kg_updates_from_round() の出力を
    GraphDiff 互換フォーマットに変換し、sse_manager.publish() で配信する。
    """

    def __init__(self) -> None:
        self._entity_index: dict[str, dict] = {}  # name -> entity data
        self._relation_index: dict[str, dict] = {}  # "src::tgt::type" -> relation data

    def _entity_to_node(self, entity: dict) -> dict:
        """KGエンティティをGraphNode互換dictに変換する。"""
        name = entity.get("name", "")
        node_id = f"kg-{_sanitize_id(name)}"
        raw_type = entity.get("type", "concept")
        node_type = _KG_TYPE_MAP.get(raw_type, "concept")
        return {
            "id": node_id,
            "label": name,
            "type": node_type,
            "importance_score": entity.get("importance_score", 0.5),
            "stance": "",
            "activity_score": 1.0,
            "sentiment_score": 0,
            "status": "active",
            "group": "knowledge",
        }

    def _relation_to_edge(self, relation: dict) -> dict | None:
        """KG関係をGraphEdge互換dictに変換する。"""
        src_name = relation.get("source", "")
        tgt_name = relation.get("target", "")
        if not src_name or not tgt_name:
            return None

        src_id = f"kg-{_sanitize_id(src_name)}"
        tgt_id = f"kg-{_sanitize_id(tgt_name)}"
        raw_type = relation.get("type", "related")
        relation_type = _KG_RELATION_MAP.get(raw_type, "influence")
        edge_id = f"kg-edge-{_sanitize_id(src_name)}-{_sanitize_id(tgt_name)}-{relation_type}"

        return {
            "id": edge_id,
            "source": src_id,
            "target": tgt_id,
            "relation_type": relation_type,
            "weight": relation.get("confidence", 0.5),
            "direction": "directed",
            "status": "active",
        }

    def _build_diff(
        self,
        updates: dict,
        round_number: int,
        phase: str,
    ) -> dict:
        """kg_updater の出力を GraphDiff 形式に変換する。"""
        added_nodes: list[dict] = []
        added_edges: list[dict] = []
        updated_nodes: list[dict] = []

        # 新エンティティ → added_nodes
        for entity in updates.get("new_entities", []):
            name = entity.get("name", "")
            if not name or name in self._entity_index:
                continue
            node = self._entity_to_node(entity)
            added_nodes.append(node)
            self._entity_index[name] = entity

        # 新関係 → added_edges
        for relation in updates.get("new_relations", []):
            src = relation.get("source", "")
            tgt = relation.get("target", "")
            key = f"{src}::{tgt}::{relation.get('type', '')}"
            if key in self._relation_index:
                continue
            edge = self._relation_to_edge(relation)
            if edge:
                added_edges.append(edge)
                self._relation_index[key] = relation

        # 既存エンティティの重要度更新 → updated_nodes
        for update in updates.get("updated_entities", []):
            name = update.get("name", "")
            delta = update.get("importance_delta", 0)
            if name in self._entity_index:
                current = self._entity_index[name].get("importance_score", 0.5)
                new_score = max(0.0, min(1.0, current + delta))
                self._entity_index[name]["importance_score"] = new_score
                node_id = f"kg-{_sanitize_id(name)}"
                updated_nodes.append({
                    "id": node_id,
                    "importance_score": new_score,
                })

        return {
            "added_nodes": added_nodes,
            "added_edges": added_edges,
            "updated_nodes": updated_nodes,
            "updated_edges": [],
            "removed_nodes": [],
            "removed_edges": [],
        }

    def _build_agent_entity_links(
        self,
        round_arguments: list[dict],
        updates: dict,
    ) -> list[dict]:
        """各エージェントがどのKGエンティティに言及したかのリンクを生成する。"""
        links: list[dict] = []
        entity_names = {
            e.get("name", "") for e in updates.get("new_entities", [])
        } | {
            u.get("name", "") for u in updates.get("updated_entities", [])
        }
        entity_names.discard("")

        if not entity_names:
            return links

        for arg in round_arguments:
            participant_index = arg.get("participant_index")
            if participant_index is None:
                continue
            agent_id = f"agent-{participant_index}"
            text = f"{arg.get('argument', '')} {arg.get('evidence', '')} {' '.join(arg.get('concerns', []))}"

            for name in entity_names:
                if name in text:
                    entity_id = f"kg-{_sanitize_id(name)}"
                    links.append({
                        "agent_id": agent_id,
                        "entity_id": entity_id,
                        "relation": "mentioned_by",
                    })

        return links

    async def extract_and_publish_from_round(
        self,
        simulation_id: str,
        round_number: int,
        round_arguments: list[dict],
        theme: str,
        existing_entity_names: set[str] | None = None,
    ) -> dict:
        """ミーティングラウンドからKGを抽出し、SSEで配信する。

        Returns:
            kg_updater形式のupdates dict (apply_kg_updates用)
        """
        updates = await extract_kg_updates_from_round(
            round_arguments, theme, existing_entity_names,
        )

        has_updates = (
            updates.get("new_entities")
            or updates.get("new_relations")
            or updates.get("updated_entities")
        )

        if has_updates:
            phase = f"council_round_{round_number}"
            diff = self._build_diff(updates, round_number, phase)
            links = self._build_agent_entity_links(round_arguments, updates)

            new_count = len(diff.get("added_nodes", []))
            total = len(self._entity_index)

            await sse_manager.publish(simulation_id, "kg_evolution", {
                "round_number": round_number,
                "phase": phase,
                "event_summary": f"ラウンド{round_number}: {new_count}個の新概念を発見",
                "diff": diff,
                "agent_entity_links": links,
                "stats": {
                    "total_entities": total,
                    "total_relations": len(self._relation_index),
                    "new_in_this_round": new_count,
                },
            })

            logger.info(
                "KG evolution published for round %d: +%d nodes, +%d edges",
                round_number,
                len(diff.get("added_nodes", [])),
                len(diff.get("added_edges", [])),
            )

        return updates

    async def extract_and_publish_from_activation(
        self,
        simulation_id: str,
        responses: list[dict],
        theme: str,
    ) -> None:
        """Activation phaseのエージェント回答からKGを抽出し、SSEで配信する。"""
        # activation responsesを擬似的なround_argumentsに変換
        pseudo_arguments = []
        for i, r in enumerate(responses):
            if r.get("_failed"):
                continue
            pseudo_arguments.append({
                "participant_index": i,
                "participant_name": r.get("name", f"agent-{i}"),
                "argument": r.get("reason", ""),
                "evidence": r.get("concern", ""),
                "concerns": [r.get("priority", "")] if r.get("priority") else [],
            })

        if not pseudo_arguments:
            return

        updates = await extract_kg_updates_from_round(
            pseudo_arguments, theme,
        )

        has_updates = (
            updates.get("new_entities")
            or updates.get("new_relations")
            or updates.get("updated_entities")
        )

        if has_updates:
            diff = self._build_diff(updates, 0, "activation")
            links = self._build_agent_entity_links(pseudo_arguments, updates)

            new_count = len(diff.get("added_nodes", []))

            await sse_manager.publish(simulation_id, "kg_evolution", {
                "round_number": 0,
                "phase": "activation",
                "event_summary": f"市民の声から{new_count}個の概念を抽出",
                "diff": diff,
                "agent_entity_links": links,
                "stats": {
                    "total_entities": len(self._entity_index),
                    "total_relations": len(self._relation_index),
                    "new_in_this_round": new_count,
                },
            })

            logger.info(
                "KG evolution published from activation: +%d nodes, +%d edges",
                len(diff.get("added_nodes", [])),
                len(diff.get("added_edges", [])),
            )

    def seed_from_existing(self, entities: list[dict], relations: list[dict]) -> None:
        """既存のKGエンティティ/関係でインデックスを初期化する。"""
        for e in entities:
            name = e.get("name", "")
            if name:
                self._entity_index[name] = e
        for r in relations:
            src = r.get("source", "")
            tgt = r.get("target", "")
            key = f"{src}::{tgt}::{r.get('type', '')}"
            self._relation_index[key] = r

    async def publish_initial_kg(self, simulation_id: str) -> None:
        """既存KGの初期状態をSSEで配信する（seed_from_existing後に呼ぶ）。"""
        if not self._entity_index:
            return

        added_nodes = [self._entity_to_node(e) for e in self._entity_index.values()]
        added_edges = []
        for r in self._relation_index.values():
            edge = self._relation_to_edge(r)
            if edge:
                added_edges.append(edge)

        await sse_manager.publish(simulation_id, "kg_evolution", {
            "round_number": -1,
            "phase": "initial",
            "event_summary": f"初期KG: {len(added_nodes)}個のエンティティ",
            "diff": {
                "added_nodes": added_nodes,
                "added_edges": added_edges,
                "updated_nodes": [],
                "updated_edges": [],
                "removed_nodes": [],
                "removed_edges": [],
            },
            "agent_entity_links": [],
            "stats": {
                "total_entities": len(self._entity_index),
                "total_relations": len(self._relation_index),
                "new_in_this_round": len(added_nodes),
            },
        })
