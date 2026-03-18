"""因果推論エンジン: world_stateからDAG構築 + 介入効果推定"""

import logging
from collections import defaultdict

from src.app.llm.client import llm_client
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


class CausalGraph:
    """因果DAG: エンティティ間の因果関係を表現する。"""

    def __init__(self):
        self._edges: dict[str, list[tuple[str, float]]] = defaultdict(list)  # source -> [(target, weight)]
        self._reverse: dict[str, list[tuple[str, float]]] = defaultdict(list)  # target -> [(source, weight)]

    def add_edge(self, source: str, target: str, weight: float = 1.0) -> None:
        self._edges[source].append((target, weight))
        self._reverse[target].append((source, weight))

    def get_effects(self, node: str, depth: int = 3) -> list[tuple[str, float]]:
        """ノードから波及する効果を計算する（BFS）。"""
        visited = set()
        effects = []
        queue = [(node, 1.0, 0)]

        while queue:
            current, accumulated_weight, current_depth = queue.pop(0)
            if current in visited or current_depth > depth:
                continue
            visited.add(current)

            if current != node:
                effects.append((current, accumulated_weight))

            for target, weight in self._edges.get(current, []):
                if target not in visited:
                    queue.append((target, accumulated_weight * weight, current_depth + 1))

        effects.sort(key=lambda x: x[1], reverse=True)
        return effects

    def get_causes(self, node: str, depth: int = 3) -> list[tuple[str, float]]:
        """ノードの原因を逆方向に辿る。"""
        visited = set()
        causes = []
        queue = [(node, 1.0, 0)]

        while queue:
            current, accumulated_weight, current_depth = queue.pop(0)
            if current in visited or current_depth > depth:
                continue
            visited.add(current)

            if current != node:
                causes.append((current, accumulated_weight))

            for source, weight in self._reverse.get(current, []):
                if source not in visited:
                    queue.append((source, accumulated_weight * weight, current_depth + 1))

        causes.sort(key=lambda x: x[1], reverse=True)
        return causes

    @property
    def nodes(self) -> set[str]:
        nodes = set(self._edges.keys())
        for targets in self._edges.values():
            for t, _ in targets:
                nodes.add(t)
        return nodes


class CausalReasoningEngine:
    """因果推論: world_stateの関係からDAGを構築し、介入効果を推定する。"""

    def __init__(self):
        self._graph = CausalGraph()

    def build_graph(self, world_state: dict) -> CausalGraph:
        """world_stateのrelationsから因果DAGを構築する。"""
        self._graph = CausalGraph()

        for relation in world_state.get("relations", []):
            source = relation.get("source", "")
            target = relation.get("target", "")
            weight = relation.get("weight", 0.5)
            rel_type = relation.get("relation_type", "")

            # 因果的関係のみDAGに追加
            if rel_type in ("influence", "dependency", "supply", "regulation"):
                self._graph.add_edge(source, target, weight)
            elif rel_type in ("cooperation", "competition"):
                # 双方向の影響
                self._graph.add_edge(source, target, weight * 0.5)
                self._graph.add_edge(target, source, weight * 0.5)

        logger.info("Causal graph built: %d nodes", len(self._graph.nodes))
        return self._graph

    def compute_ripple_effects(
        self, entity_id: str, change_magnitude: float = 1.0, depth: int = 3,
    ) -> list[dict]:
        """エンティティへの変化の波及効果を計算する（LLM不要）。"""
        effects = self._graph.get_effects(entity_id, depth)
        return [
            {
                "entity_id": eid,
                "impact_strength": weight * change_magnitude,
                "hops": i + 1,
            }
            for i, (eid, weight) in enumerate(effects)
        ]

    def find_root_causes(self, entity_id: str, depth: int = 3) -> list[dict]:
        """エンティティの状態変化の根本原因を探索する（LLM不要）。"""
        causes = self._graph.get_causes(entity_id, depth)
        return [
            {"entity_id": eid, "influence_strength": weight}
            for eid, weight in causes
        ]

    async def estimate_intervention(
        self,
        session,
        run_id: str,
        entity_id: str,
        intervention: str,
        world_state: dict,
    ) -> dict:
        """介入の効果をLLMで推定する。"""
        # まず波及先を因果グラフから取得
        ripple = self.compute_ripple_effects(entity_id)

        entity_label = ""
        for e in world_state.get("entities", []):
            if e.get("id") == entity_id:
                entity_label = e.get("label", entity_id)
                break

        affected_labels = []
        entity_map = {e.get("id"): e.get("label", e.get("id")) for e in world_state.get("entities", [])}
        for r in ripple[:10]:
            affected_labels.append(f"{entity_map.get(r['entity_id'], r['entity_id'])} (影響度: {r['impact_strength']:.2f})")

        system_prompt = """あなたは因果推論の専門家です。
介入の直接効果と波及効果を推定してください。"""

        user_prompt = f"""以下の介入の効果を推定してください。

## 介入対象
エンティティ: {entity_label} ({entity_id})
介入内容: {intervention}

## 因果グラフから推定される影響先
{chr(10).join(f"- {l}" for l in affected_labels) or "直接的な影響先なし"}

## 出力形式（JSON）
{{
  "direct_effects": [
    {{"entity_id": "ID", "description": "直接効果", "magnitude": 0.0-1.0}}
  ],
  "indirect_effects": [
    {{"entity_id": "ID", "description": "間接効果", "magnitude": 0.0-1.0}}
  ],
  "counterfactual": "介入しなかった場合の予測",
  "confidence": 0.0-1.0
}}

重要: 必ず有効な JSON のみを出力してください。"""

        result, usage = await llm_client.call_with_retry(
            task_name="causal_intervene",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        await record_usage(session, run_id, "causal_intervene", usage)

        if isinstance(result, dict):
            return result
        return {"direct_effects": [], "indirect_effects": [], "confidence": 0.0}
