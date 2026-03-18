"""GraphRAGPipeline: 全ステップのオーケストレーション"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.models.kg_node import KGNode
from src.app.models.kg_edge import KGEdge
from src.app.models.community import Community
from src.app.services.cost_tracker import record_usage
from src.app.services.graphrag.chunker import SemanticChunker
from src.app.services.graphrag.entity_extractor import EntityExtractor
from src.app.services.graphrag.relation_extractor import RelationExtractor
from src.app.services.graphrag.dedup_resolver import DedupResolver
from src.app.services.graphrag.community_detector import CommunityDetector

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """GraphRAGパイプラインの出力を保持する構造体。"""

    def __init__(
        self,
        entities: list[dict],
        relations: list[dict],
        communities: list[dict],
    ):
        self.entities = entities
        self.relations = relations
        self.communities = communities

    def to_world_state_data(self) -> dict:
        """KGからworld_stateデータを構築する。"""
        ws_entities = []
        for e in self.entities:
            ws_entities.append({
                "id": e.get("id", e["name"]),
                "label": e["name"],
                "entity_type": e.get("type", "unknown"),
                "description": e.get("description", ""),
                "importance_score": e.get("importance_score", 0.5),
                "stance": "",
                "activity_score": 0.5,
                "sentiment_score": 0.0,
                "status": "active",
                "group": e.get("community_label", ""),
                "aliases": e.get("aliases", []),
            })

        ws_relations = []
        for r in self.relations:
            ws_relations.append({
                "id": f"rel_{r.get('source', '')}_{r.get('target', '')}",
                "source": r.get("source", ""),
                "target": r.get("target", ""),
                "relation_type": r.get("type", "related"),
                "weight": r.get("confidence", 0.5),
                "direction": "directed",
            })

        community_summaries = [
            {"community": c["community_index"], "summary": c["summary"], "members": c["member_names"]}
            for c in self.communities
        ]

        return {
            "entities": ws_entities,
            "relations": ws_relations,
            "communities": community_summaries,
        }


class GraphRAGPipeline:
    """文書からKGを構築するパイプライン。"""

    def __init__(self):
        config = settings.load_graphrag_config()
        self.chunk_size = config.get("chunk_size", 2000)
        self.chunk_overlap = config.get("chunk_overlap", 200)
        self.extraction_passes = config.get("extraction_passes", 2)
        self.dedup_threshold = config.get("dedup_threshold", 0.85)
        self.community_min_size = config.get("community_min_size", 3)

    async def run(
        self,
        session: AsyncSession,
        run_id: str,
        document_text: str,
    ) -> KnowledgeGraph:
        """GraphRAGパイプラインを実行する。

        1. セマンティックチャンク分割
        2. エンティティ抽出（並列）
        3. 重複解決
        4. 関係抽出（並列）
        5. コミュニティ検出 + サマリー生成
        6. DB保存
        """
        logger.info(f"Starting GraphRAG pipeline for run {run_id} (doc_len={len(document_text)})")

        # 1. チャンク分割
        chunker = SemanticChunker(self.chunk_size, self.chunk_overlap)
        chunks = chunker.chunk(document_text)
        logger.info(f"Split document into {len(chunks)} chunks")

        # 2. エンティティ抽出（複数パスで精度向上）
        extractor = EntityExtractor()
        all_entities = []
        for pass_num in range(self.extraction_passes):
            entities = await extractor.extract_from_chunks(chunks, run_id)
            all_entities.extend(entities)
            logger.info(f"Pass {pass_num + 1}: extracted {len(entities)} entities")

        # 3. 重複解決
        resolver = DedupResolver(threshold=self.dedup_threshold)
        deduped_entities = await resolver.deduplicate(all_entities)

        # 4. 関係抽出
        rel_extractor = RelationExtractor()
        relations = await rel_extractor.extract_relations(deduped_entities, chunks)

        # 5. コミュニティ検出
        detector = CommunityDetector(min_size=self.community_min_size)
        communities = await detector.detect_and_summarize(deduped_entities, relations)

        # コミュニティラベルをエンティティに付与
        for comm in communities:
            for name in comm["member_names"]:
                for e in deduped_entities:
                    if e["name"] == name:
                        e["community_label"] = f"community_{comm['community_index']}"

        # 6. DB保存
        entity_id_map = {}
        for e in deduped_entities:
            db_id = str(uuid.uuid4())
            entity_id_map[e["name"]] = db_id
            e["id"] = db_id
            node = KGNode(
                id=db_id,
                run_id=run_id,
                label=e["name"],
                node_type=e.get("type", "unknown"),
                description=e.get("description", ""),
                aliases=e.get("aliases", []),
                properties={k: v for k, v in e.items() if k not in ("name", "type", "description", "aliases", "embedding", "source_chunk", "id", "community_label")},
                community_id=next((c["community_index"] for c in communities if e["name"] in c["member_names"]), None),
                embedding=e.get("embedding"),
            )
            session.add(node)

        for r in relations:
            source_id = entity_id_map.get(r.get("source", ""), "")
            target_id = entity_id_map.get(r.get("target", ""), "")
            if source_id and target_id:
                edge = KGEdge(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    source_node_id=source_id,
                    target_node_id=target_id,
                    relation_type=r.get("type", "related"),
                    description=r.get("evidence", ""),
                    weight=1.0,
                    confidence=r.get("confidence", 1.0),
                    evidence_text=r.get("evidence", ""),
                )
                session.add(edge)

        for c in communities:
            comm = Community(
                id=str(uuid.uuid4()),
                run_id=run_id,
                community_index=c["community_index"],
                summary=c["summary"],
                member_node_ids=[entity_id_map.get(n, n) for n in c["member_names"]],
                level=c.get("level", 0),
            )
            session.add(comm)

        await session.flush()

        kg = KnowledgeGraph(
            entities=deduped_entities,
            relations=relations,
            communities=communities,
        )

        logger.info(
            f"GraphRAG complete: {len(deduped_entities)} entities, "
            f"{len(relations)} relations, {len(communities)} communities"
        )
        return kg
