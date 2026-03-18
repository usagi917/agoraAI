"""CommunityDetector: NetworkX Louvain法でコミュニティ検出 + LLMサマリー"""

import asyncio
import logging

import networkx as nx

from src.app.llm.client import llm_client
from src.app.llm.prompts import COMMUNITY_SUMMARY_SYSTEM, COMMUNITY_SUMMARY_USER

logger = logging.getLogger(__name__)


class CommunityDetector:
    def __init__(self, min_size: int = 3):
        self.min_size = min_size

    async def detect_and_summarize(
        self,
        entities: list[dict],
        relations: list[dict],
    ) -> list[dict]:
        """Louvain法でコミュニティを検出し、LLMでサマリーを生成する。"""
        G = self._build_graph(entities, relations)

        if G.number_of_nodes() < self.min_size:
            return []

        # Louvain法でコミュニティ検出
        try:
            communities = nx.community.louvain_communities(G, seed=42)
        except Exception as e:
            logger.warning(f"Louvain community detection failed: {e}")
            return []

        # min_size以上のコミュニティのみ
        valid_communities = [c for c in communities if len(c) >= self.min_size]

        if not valid_communities:
            return []

        # エンティティ名マップ
        entity_map = {e["name"]: e for e in entities}

        # 各コミュニティのサマリーを生成
        tasks = []
        for idx, community_nodes in enumerate(valid_communities):
            members = [entity_map.get(n, {"name": n}) for n in community_nodes]
            member_relations = [
                r for r in relations
                if r.get("source") in community_nodes and r.get("target") in community_nodes
            ]
            tasks.append(self._summarize_community(idx, members, member_relations))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        community_data = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Community summary failed for {idx}: {result}")
                summary = ""
            else:
                summary = result

            community_data.append({
                "community_index": idx,
                "member_names": list(valid_communities[idx]),
                "member_count": len(valid_communities[idx]),
                "summary": summary,
                "level": 0,
            })

        logger.info(f"Detected {len(community_data)} communities")
        return community_data

    def _build_graph(self, entities: list[dict], relations: list[dict]) -> nx.Graph:
        """エンティティと関係からNetworkXグラフを構築する。"""
        G = nx.Graph()
        for e in entities:
            G.add_node(e["name"], **{k: v for k, v in e.items() if k != "name" and k != "embedding"})

        for r in relations:
            source = r.get("source", "")
            target = r.get("target", "")
            if source in G.nodes and target in G.nodes:
                G.add_edge(
                    source, target,
                    relation_type=r.get("type", "related"),
                    weight=r.get("confidence", 1.0),
                )
        return G

    async def _summarize_community(
        self, idx: int, members: list[dict], relations: list[dict]
    ) -> str:
        """コミュニティのサマリーをLLMで生成する。"""
        members_desc = "\n".join(
            f"- {m['name']}: {m.get('description', '')}" for m in members
        )
        relations_desc = "\n".join(
            f"- {r.get('source')} → {r.get('target')}: {r.get('type', '')}"
            for r in relations[:20]
        )

        user_prompt = COMMUNITY_SUMMARY_USER.format(
            community_index=idx,
            members=members_desc,
            relations=relations_desc,
        )

        result, _usage = await llm_client.call(
            task_name="community_summary",
            system_prompt=COMMUNITY_SUMMARY_SYSTEM,
            user_prompt=user_prompt,
        )

        if isinstance(result, dict):
            return result.get("summary", "")
        return str(result) if result else ""
