"""世界モデル構築: 文書 → entities + relations + world_state_seed"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.llm.client import llm_client
from src.app.llm.prompts import WORLD_BUILD_SYSTEM, WORLD_BUILD_USER
from src.app.llm.validator import validate_world_build
from src.app.models.entity import Entity
from src.app.models.relation import Relation
from src.app.models.run import Run
from src.app.models.world_state import WorldState
from src.app.services.cost_tracker import record_usage
from src.app.services.quality import build_evidence_bundle
from src.app.services.verification import (
    ensure_verification_passed,
    verify_world_build_result,
)

if TYPE_CHECKING:
    from src.app.services.graphrag.pipeline import KnowledgeGraph

logger = logging.getLogger(__name__)


async def _resolve_project_id(session: AsyncSession, run_id: str) -> str | None:
    result = await session.execute(select(Run.project_id).where(Run.id == run_id))
    return result.scalar_one_or_none()


async def build_world(
    session: AsyncSession,
    run_id: str,
    document_text: str,
    template_prompt: str,
    prompt_text: str = "",
    knowledge_graph: KnowledgeGraph | None = None,
) -> dict:
    """文書から世界モデルを構築し、DB に保存する。

    knowledge_graph が渡された場合は GraphRAG の構造化データから world_state を構築し、
    8000文字制限なしで全文カバレッジを実現する。
    """

    # GraphRAG KG が利用可能な場合はそこから world_state を構築
    if knowledge_graph is not None:
        return await _build_from_knowledge_graph(
            session, run_id, knowledge_graph, document_text, template_prompt, prompt_text,
        )

    project_id = await _resolve_project_id(session, run_id)
    evidence_bundle = await build_evidence_bundle(
        session,
        project_id,
        prompt_text,
        query_text="\n".join(part for part in [template_prompt, prompt_text] if part),
        inline_document_text=document_text,
        inline_document_label="Uploaded documents",
        max_documents=4,
        max_document_chunks=3,
        max_refs=10,
        max_chars=12000,
    )

    user_prompt = WORLD_BUILD_USER.format(
        template_prompt=template_prompt,
        user_prompt=prompt_text or "（指示なし）",
        document_text=evidence_bundle["context_text"] or document_text,
    )

    result, usage = await llm_client.call_with_retry(
        task_name="world_build",
        system_prompt=WORLD_BUILD_SYSTEM,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
        validate_fn=validate_world_build,
    )

    await record_usage(session, run_id, "world_build", usage)

    if not isinstance(result, dict):
        logger.error(f"World build returned non-dict: {str(result)[:200]}")
        raise ValueError(f"世界構築の LLM 応答が JSON ではありませんでした: {str(result)[:100]}")

    verification = verify_world_build_result(result)
    ensure_verification_passed(verification, context="world_build")
    result["verification"] = verification
    result["evidence_refs"] = evidence_bundle["evidence_refs"]

    # エンティティ保存
    entity_id_map = {}
    for e in result.get("entities", []):
        db_id = str(uuid.uuid4())
        entity_id_map[e["id"]] = db_id
        entity = Entity(
            id=db_id,
            run_id=run_id,
            label=e.get("label", ""),
            entity_type=e.get("entity_type", "unknown"),
            description=e.get("description", ""),
            importance_score=float(e.get("importance_score", 0.5)),
            stance=e.get("stance", ""),
            activity_score=float(e.get("activity_score", 0.5)),
            sentiment_score=float(e.get("sentiment_score", 0.0)),
            status=e.get("status", "active"),
            group=e.get("group", ""),
            last_updated_round=0,
        )
        session.add(entity)

    # リレーション保存
    for r in result.get("relations", []):
        source_db_id = entity_id_map.get(r.get("source"), r.get("source", ""))
        target_db_id = entity_id_map.get(r.get("target"), r.get("target", ""))
        relation = Relation(
            id=str(uuid.uuid4()),
            run_id=run_id,
            source_entity_id=source_db_id,
            target_entity_id=target_db_id,
            relation_type=r.get("relation_type", "unknown"),
            weight=float(r.get("weight", 0.5)),
            direction=r.get("direction", "directed"),
            status="active",
            last_updated_round=0,
        )
        session.add(relation)

    # world_state 保存
    world_state = WorldState(
        id=str(uuid.uuid4()),
        run_id=run_id,
        round_number=0,
        state_data={
            "entities": result.get("entities", []),
            "relations": result.get("relations", []),
            "timeline": result.get("timeline", []),
            "world_summary": result.get("world_summary", ""),
            "entity_id_map": entity_id_map,
            "verification": verification,
            "evidence_refs": evidence_bundle["evidence_refs"],
        },
    )
    session.add(world_state)
    await session.flush()

    logger.info(
        f"World built for run {run_id}: "
        f"{len(result.get('entities', []))} entities, "
        f"{len(result.get('relations', []))} relations"
    )

    return result


async def _build_from_knowledge_graph(
    session: AsyncSession,
    run_id: str,
    knowledge_graph: KnowledgeGraph,
    document_text: str,
    template_prompt: str,
    prompt_text: str,
) -> dict:
    """GraphRAGのKGからworld_stateを構築する（8000文字制限なし）。"""

    kg_data = knowledge_graph.to_world_state_data()
    project_id = await _resolve_project_id(session, run_id)
    evidence_bundle = await build_evidence_bundle(
        session,
        project_id,
        prompt_text,
        query_text="\n".join(
            part
            for part in [
                template_prompt,
                prompt_text,
                " ".join(entity["label"] for entity in kg_data["entities"][:12]),
            ]
            if part
        ),
        inline_document_text=document_text,
        inline_document_label="Uploaded documents",
        max_documents=4,
        max_document_chunks=2,
        max_refs=8,
        max_chars=7000,
    )

    # LLMで世界サマリーとタイムラインを生成（KGデータをコンテキストとして渡す）
    compact_entities = json.dumps(
        [{"label": e["label"], "type": e["entity_type"]} for e in kg_data["entities"][:50]],
        ensure_ascii=False,
    )
    compact_relations = json.dumps(
        [{"source": r["source"], "target": r["target"], "type": r["relation_type"]} for r in kg_data["relations"][:50]],
        ensure_ascii=False,
    )
    community_info = json.dumps(kg_data.get("communities", [])[:10], ensure_ascii=False)

    user_prompt = WORLD_BUILD_USER.format(
        template_prompt=template_prompt,
        user_prompt=prompt_text or "（指示なし）",
        document_text=(
            f"## ナレッジグラフから抽出済みの構造化データ\n\n"
            f"### エンティティ ({len(kg_data['entities'])}件)\n{compact_entities}\n\n"
            f"### 関係 ({len(kg_data['relations'])}件)\n{compact_relations}\n\n"
            f"### コミュニティ\n{community_info}\n\n"
            f"## 関連根拠\n{evidence_bundle['context_text'] or document_text}"
        ),
    )

    result, usage = await llm_client.call_with_retry(
        task_name="world_build",
        system_prompt=WORLD_BUILD_SYSTEM,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
        validate_fn=validate_world_build,
    )

    await record_usage(session, run_id, "world_build_graphrag", usage)

    if not isinstance(result, dict):
        raise ValueError(f"GraphRAG世界構築のLLM応答がJSONではありませんでした: {str(result)[:100]}")

    verification = verify_world_build_result(result)
    ensure_verification_passed(verification, context="world_build_graphrag")
    result["verification"] = verification
    result["evidence_refs"] = evidence_bundle["evidence_refs"]

    # KGからのエンティティとLLM結果をマージ
    # LLM結果のエンティティをベースに、KGの追加情報を補完
    llm_entities = {e["id"]: e for e in result.get("entities", [])}
    for kg_e in kg_data["entities"]:
        if kg_e["id"] not in llm_entities:
            result.setdefault("entities", []).append(kg_e)

    # エンティティ保存
    entity_id_map = {}
    for e in result.get("entities", []):
        db_id = str(uuid.uuid4())
        entity_id_map[e["id"]] = db_id
        entity = Entity(
            id=db_id,
            run_id=run_id,
            label=e.get("label", ""),
            entity_type=e.get("entity_type", "unknown"),
            description=e.get("description", ""),
            importance_score=float(e.get("importance_score", 0.5)),
            stance=e.get("stance", ""),
            activity_score=float(e.get("activity_score", 0.5)),
            sentiment_score=float(e.get("sentiment_score", 0.0)),
            status=e.get("status", "active"),
            group=e.get("group", ""),
            last_updated_round=0,
        )
        session.add(entity)

    # リレーション保存
    for r in result.get("relations", []):
        source_db_id = entity_id_map.get(r.get("source"), r.get("source", ""))
        target_db_id = entity_id_map.get(r.get("target"), r.get("target", ""))
        relation = Relation(
            id=str(uuid.uuid4()),
            run_id=run_id,
            source_entity_id=source_db_id,
            target_entity_id=target_db_id,
            relation_type=r.get("relation_type", "unknown"),
            weight=float(r.get("weight", 0.5)),
            direction=r.get("direction", "directed"),
            status="active",
            last_updated_round=0,
        )
        session.add(relation)

    # world_state 保存
    world_state = WorldState(
        id=str(uuid.uuid4()),
        run_id=run_id,
        round_number=0,
        state_data={
            "entities": result.get("entities", []),
            "relations": result.get("relations", []),
            "timeline": result.get("timeline", []),
            "world_summary": result.get("world_summary", ""),
            "entity_id_map": entity_id_map,
            "communities": kg_data.get("communities", []),
            "verification": verification,
            "evidence_refs": evidence_bundle["evidence_refs"],
        },
    )
    session.add(world_state)
    await session.flush()

    logger.info(
        f"World built from KG for run {run_id}: "
        f"{len(result.get('entities', []))} entities, "
        f"{len(result.get('relations', []))} relations"
    )

    return result
