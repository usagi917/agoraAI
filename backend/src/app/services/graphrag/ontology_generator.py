"""OntologyGenerator: テーマ + ドキュメントから動的にエンティティ型・関係型を設計する"""

import logging

from src.app.llm.multi_client import multi_llm_client

logger = logging.getLogger(__name__)

DEFAULT_ENTITY_TYPES = [
    "person", "organization", "concept", "technology",
    "location", "event", "policy", "market", "resource",
]

DEFAULT_RELATION_TYPES = [
    "competition", "cooperation", "regulation", "supply",
    "influence", "dependency", "ownership", "alliance", "conflict",
]


async def generate_ontology(
    theme: str,
    document_preview: str,
    max_entity_types: int = 10,
    max_relation_types: int = 10,
) -> dict:
    """テーマとドキュメントからドメイン特化オントロジーを動的生成する。

    Returns:
        {
            "entity_types": [{"name": str, "description": str, "examples": [str]}],
            "relation_types": [{"name": str, "description": str, "directed": bool}],
            "extraction_guidance": str,
        }
    """
    multi_llm_client.initialize()

    system_prompt = (
        "あなたはナレッジグラフのオントロジー設計の専門家です。\n"
        "テーマとドキュメントの内容に基づいて、エンティティ型と関係型を設計してください。\n\n"
        "設計ルール:\n"
        f"1. エンティティ型は最大{max_entity_types}個（ドメイン固有8個 + 汎用2個 Person, Organization）\n"
        f"2. 関係型は最大{max_relation_types}個（UPPER_SNAKE_CASE）\n"
        "3. 各型にはこのドメインでの具体例を2-3個付与すること\n"
        "4. 抽象的すぎる型は避け、テキストから実際に抽出可能な型にすること\n"
        "5. extraction_guidance にはこのドメインでの抽出時の注意点を記載\n\n"
        "出力は必ず以下のJSON形式のみで:\n"
        "{\n"
        '  "entity_types": [\n'
        '    {"name": "PascalCase型名", "description": "説明", "examples": ["例1", "例2"]}\n'
        "  ],\n"
        '  "relation_types": [\n'
        '    {"name": "UPPER_SNAKE_CASE型名", "description": "説明", "directed": true/false}\n'
        "  ],\n"
        '  "extraction_guidance": "このドメインでの抽出時の注意点"\n'
        "}"
    )

    user_prompt = (
        f"テーマ: {theme}\n\n"
        f"ドキュメント冒頭（最初の2000文字）:\n{document_preview[:2000]}\n\n"
        "上記のテーマとドキュメントに最適なオントロジーを設計してください。"
    )

    try:
        result, usage = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=2048,
        )

        if isinstance(result, dict) and "entity_types" in result:
            logger.info(
                "Generated dynamic ontology: %d entity types, %d relation types",
                len(result.get("entity_types", [])),
                len(result.get("relation_types", [])),
            )
            return result

        logger.warning("Ontology generation returned non-dict, using defaults")
    except Exception as e:
        logger.error("Ontology generation failed: %s", e)

    # フォールバック: デフォルトオントロジー
    return {
        "entity_types": [
            {"name": t, "description": "", "examples": []}
            for t in DEFAULT_ENTITY_TYPES
        ],
        "relation_types": [
            {"name": t, "description": "", "directed": True}
            for t in DEFAULT_RELATION_TYPES
        ],
        "extraction_guidance": "",
    }


def build_extraction_prompt_from_ontology(ontology: dict) -> tuple[str, str]:
    """オントロジーからエンティティ抽出プロンプトの補足部分を生成する。

    Returns:
        (entity_type_guidance, relation_type_guidance)
    """
    # エンティティ型ガイダンス
    entity_parts = []
    for et in ontology.get("entity_types", []):
        name = et.get("name", "")
        desc = et.get("description", "")
        examples = et.get("examples", [])
        ex_str = f"（例: {', '.join(examples)}）" if examples else ""
        entity_parts.append(f"- {name}: {desc}{ex_str}")
    entity_guidance = "使用可能なエンティティ型:\n" + "\n".join(entity_parts) if entity_parts else ""

    # 関係型ガイダンス
    relation_parts = []
    for rt in ontology.get("relation_types", []):
        name = rt.get("name", "")
        desc = rt.get("description", "")
        relation_parts.append(f"- {name}: {desc}")
    relation_guidance = "使用可能な関係型:\n" + "\n".join(relation_parts) if relation_parts else ""

    extraction_note = ontology.get("extraction_guidance", "")
    if extraction_note:
        entity_guidance += f"\n\n抽出時の注意: {extraction_note}"

    return entity_guidance, relation_guidance
