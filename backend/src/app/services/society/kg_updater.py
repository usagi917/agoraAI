"""KG Updater: ミーティング議論から新しいエンティティ・関係を KG に追加する"""

import logging

from src.app.llm.multi_client import multi_llm_client

logger = logging.getLogger(__name__)


async def extract_kg_updates_from_round(
    round_arguments: list[dict],
    theme: str,
    existing_entity_names: set[str] | None = None,
) -> dict:
    """1ラウンドのミーティング議論から新エンティティ・関係を抽出する。

    Returns:
        {
            "new_entities": [{"name": str, "type": str, "description": str, "importance_score": float}],
            "new_relations": [{"source": str, "target": str, "type": str, "evidence": str, "confidence": float}],
            "updated_entities": [{"name": str, "importance_delta": float, "reason": str}],
        }
    """
    multi_llm_client.initialize()

    existing = existing_entity_names or set()

    # 議論内容をテキスト化
    discussion_parts = []
    for arg in round_arguments:
        name = arg.get("participant_name", "参加者")
        argument = arg.get("argument", "")
        evidence = arg.get("evidence", "")
        concerns = arg.get("concerns", [])
        parts = [f"[{name}] {argument}"]
        if evidence:
            parts.append(f"  根拠: {evidence}")
        if concerns:
            parts.append(f"  懸念: {', '.join(concerns[:3])}")
        discussion_parts.append("\n".join(parts))

    discussion_text = "\n\n".join(discussion_parts)

    if not discussion_text.strip():
        return {"new_entities": [], "new_relations": [], "updated_entities": []}

    existing_list = ", ".join(list(existing)[:30]) if existing else "なし"

    system_prompt = (
        "あなたはナレッジグラフの更新専門家です。\n"
        "ミーティング議論から、新たに言及された概念・組織・リスク・機会を抽出してください。\n"
        "既存のエンティティと重複しないもののみ抽出してください。\n\n"
        "出力は必ずJSON形式のみで:\n"
        "{\n"
        '  "new_entities": [{"name": "名前", "type": "concept|risk|opportunity|stakeholder|metric", '
        '"description": "説明", "importance_score": 0.0-1.0}],\n'
        '  "new_relations": [{"source": "エンティティ名", "target": "エンティティ名", '
        '"type": "関係型", "evidence": "根拠", "confidence": 0.0-1.0}],\n'
        '  "updated_entities": [{"name": "既存エンティティ名", "importance_delta": -0.2-0.2, "reason": "理由"}]\n'
        "}"
    )

    user_prompt = (
        f"テーマ: {theme}\n\n"
        f"既存エンティティ: {existing_list}\n\n"
        f"議論内容:\n{discussion_text}\n\n"
        "上記の議論から新たに登場した概念やリスク、既存エンティティの重要度変化を抽出してください。"
    )

    try:
        result, usage = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=2048,
        )

        if isinstance(result, dict):
            new_entities = result.get("new_entities", [])
            new_relations = result.get("new_relations", [])
            updated = result.get("updated_entities", [])

            logger.info(
                "KG update extracted: %d new entities, %d new relations, %d updates",
                len(new_entities), len(new_relations), len(updated),
            )
            return {
                "new_entities": new_entities,
                "new_relations": new_relations,
                "updated_entities": updated,
            }

    except Exception as e:
        logger.warning("KG update extraction failed: %s", e)

    return {"new_entities": [], "new_relations": [], "updated_entities": []}


def apply_kg_updates(
    kg_entities: list[dict],
    kg_relations: list[dict],
    updates: dict,
) -> tuple[list[dict], list[dict]]:
    """KG 更新を既存のエンティティ・関係リストに適用する。

    Returns:
        (updated_entities, updated_relations)
    """
    entity_name_set = {e["name"] for e in kg_entities}

    # 新エンティティ追加
    for new_e in updates.get("new_entities", []):
        name = new_e.get("name", "")
        if name and name not in entity_name_set:
            kg_entities.append({
                "name": name,
                "type": new_e.get("type", "concept"),
                "description": new_e.get("description", ""),
                "importance_score": new_e.get("importance_score", 0.5),
                "source_chunk": -1,  # 議論から生成
                "aliases": [],
            })
            entity_name_set.add(name)

    # 新関係追加
    for new_r in updates.get("new_relations", []):
        src = new_r.get("source", "")
        tgt = new_r.get("target", "")
        if src in entity_name_set and tgt in entity_name_set:
            kg_relations.append(new_r)

    # 既存エンティティの重要度更新
    for update in updates.get("updated_entities", []):
        name = update.get("name", "")
        delta = update.get("importance_delta", 0)
        for e in kg_entities:
            if e["name"] == name:
                current = e.get("importance_score", 0.5)
                e["importance_score"] = max(0.0, min(1.0, current + delta))
                break

    return kg_entities, kg_relations
