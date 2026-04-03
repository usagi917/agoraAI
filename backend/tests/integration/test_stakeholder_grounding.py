"""統合テスト: KG-Anchored Stakeholder Grounding

パイプライン全体を通したテスト:
  KnowledgeGraph → map_stakeholders → generate_agents(seeds) → 結果検証

Pass criteria: 生成エージェントの ≥80% が source_entity_id をシード UUID と一致させること

このテストは LLM 呼び出しをモックするため、外部サービス不要で実行可能。
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.factories import make_llm_response
from src.app.services.graphrag.pipeline import KnowledgeGraph
from src.app.services.graphrag.stakeholder_mapper import (
    MIN_STAKEHOLDER_COUNT,
    map_stakeholders,
)
from src.app.services.agent_generator import generate_agents


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_kg(
    n_persons: int = 10,
    n_locations: int = 3,
    n_relations: int = 8,
) -> KnowledgeGraph:
    """テスト用の KnowledgeGraph を生成する。"""
    entities = []
    for i in range(n_persons):
        entities.append({
            "id": str(uuid.uuid4()),
            "name": f"ステークホルダー{i:02d}",
            "type": "PERSON" if i % 2 == 0 else "ORGANIZATION",
            "description": f"政策立案に関わる人物または組織。コミュニティ {'A' if i < 5 else 'B'} 所属。",
            "community_label": "A" if i < 5 else "B",
            "importance_score": 0.5,  # unreliable per spec B — degree used instead
        })
    for j in range(n_locations):
        entities.append({
            "id": str(uuid.uuid4()),
            "name": f"場所{j}",
            "type": "LOCATION",
            "description": "地域エンティティ",
            "community_label": "C",
            "importance_score": 0.5,
        })

    person_names = [e["name"] for e in entities if e["type"] in ("PERSON", "ORGANIZATION")]
    relations = [
        {"source": person_names[i % len(person_names)],
         "target": person_names[(i + 1) % len(person_names)],
         "type": "KNOWS"}
        for i in range(n_relations)
    ]

    return KnowledgeGraph(entities=entities, relations=relations, communities=[])


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Test 1: map_stakeholders returns ≥ MIN_STAKEHOLDER_COUNT seeds
# ---------------------------------------------------------------------------

def test_map_stakeholders_returns_enough_seeds():
    """KG から MIN_STAKEHOLDER_COUNT 以上のシードが返ること。"""
    kg = _make_kg(n_persons=10)
    seeds = map_stakeholders(kg)
    assert len(seeds) >= MIN_STAKEHOLDER_COUNT, (
        f"Expected ≥{MIN_STAKEHOLDER_COUNT} seeds, got {len(seeds)}"
    )


def test_map_stakeholders_all_have_valid_uuids():
    """全シードが有効な UUID の entity_id を持つこと。"""
    kg = _make_kg(n_persons=8)
    seeds = map_stakeholders(kg)
    for seed in seeds:
        parsed = uuid.UUID(seed.entity_id)  # raises if invalid
        assert str(parsed) == seed.entity_id


def test_map_stakeholders_excludes_locations():
    """LOCATION エンティティはシードに含まれないこと。"""
    kg = _make_kg(n_persons=6, n_locations=5)
    seeds = map_stakeholders(kg)
    for seed in seeds:
        assert seed.entity_type.upper() in {"PERSON", "ORGANIZATION", "GROUP", "STAKEHOLDER"}


# ---------------------------------------------------------------------------
# Test 2: generate_agents with seeds — ≥80% source_entity_id match
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grounding_pass_criteria_80pct(mock_session):
    """≥80% の生成エージェントが source_entity_id をシード UUID と一致させること。

    シミュレーション: 10 シードのうち 9 件を正しい UUID で返し、1 件を間違えた UUID で返す
    → 9/10 = 90% ≥ 80% → PASS
    """
    kg = _make_kg(n_persons=10, n_relations=10)
    seeds = map_stakeholders(kg, max_count=10)
    assert len(seeds) >= MIN_STAKEHOLDER_COUNT

    # LLM が返すエージェント: 9 件は正しい UUID、1 件は間違い
    correct_agents = [
        {
            "id": str(uuid.uuid4()),
            "name": s.name,
            "role": "stakeholder",
            "source_entity_id": s.entity_id,  # 正しい UUID
            "goals": ["政策推進"],
        }
        for s in seeds[:9]
    ]
    wrong_agent = {
        "id": str(uuid.uuid4()),
        "name": "未知のエージェント",
        "role": "stakeholder",
        "source_entity_id": str(uuid.uuid4()),  # 間違い UUID
        "goals": [],
    }
    payload = {"agents": correct_agents + [wrong_agent]}

    with patch(
        "src.app.services.agent_generator.llm_client.call_with_retry",
        new=AsyncMock(return_value=make_llm_response(payload)),
    ), patch(
        "src.app.services.agent_generator.record_usage",
        new=AsyncMock(),
    ):
        result = await generate_agents(
            mock_session, "integration-run-1", {}, "テンプレート", stakeholder_seeds=seeds,
        )

    agents = result["agents"]
    seed_ids = {s.entity_id for s in seeds}
    matched = [a for a in agents if a.get("source_entity_id") in seed_ids]
    match_rate = len(matched) / len(agents) if agents else 0.0

    assert match_rate >= 0.80, (
        f"Pass criteria failed: {len(matched)}/{len(agents)} = {match_rate:.0%} < 80%"
    )


@pytest.mark.asyncio
async def test_grounding_all_agents_have_source_entity_id(mock_session):
    """seeds パスで生成されたエージェントは全件 source_entity_id を持つこと。"""
    kg = _make_kg(n_persons=6, n_relations=4)
    seeds = map_stakeholders(kg, max_count=6)
    assert len(seeds) >= MIN_STAKEHOLDER_COUNT

    agents_payload = [
        {
            "id": str(uuid.uuid4()),
            "name": s.name,
            "role": "stakeholder",
            "source_entity_id": s.entity_id,
            "goals": [],
        }
        for s in seeds
    ]

    with patch(
        "src.app.services.agent_generator.llm_client.call_with_retry",
        new=AsyncMock(return_value=make_llm_response({"agents": agents_payload})),
    ), patch(
        "src.app.services.agent_generator.record_usage",
        new=AsyncMock(),
    ):
        result = await generate_agents(
            mock_session, "integration-run-2", {}, "テンプレート", stakeholder_seeds=seeds,
        )

    for agent in result["agents"]:
        assert "source_entity_id" in agent
        assert agent["source_entity_id"] is not None


@pytest.mark.asyncio
async def test_grounding_fallback_when_all_uuids_wrong(mock_session):
    """全エージェントが間違い UUID → generic フォールバックが実行されること。"""
    kg = _make_kg(n_persons=6)
    seeds = map_stakeholders(kg, max_count=6)
    assert len(seeds) >= MIN_STAKEHOLDER_COUNT

    all_wrong_payload = {"agents": [
        {
            "id": str(uuid.uuid4()),
            "name": f"bad_{i}",
            "role": "r",
            "source_entity_id": str(uuid.uuid4()),  # 全て間違い
            "goals": [],
        }
        for i in range(len(seeds))
    ]}
    generic_payload = {"agents": [
        {"id": str(uuid.uuid4()), "name": "汎用エージェント", "role": "citizen", "goals": []}
    ]}

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return make_llm_response(all_wrong_payload if call_count == 1 else generic_payload)

    with patch(
        "src.app.services.agent_generator.llm_client.call_with_retry",
        new=side_effect,
    ), patch(
        "src.app.services.agent_generator.record_usage",
        new=AsyncMock(),
    ):
        result = await generate_agents(
            mock_session, "integration-run-3",
            {"entities": [], "relations": [], "world_summary": ""},
            "テンプレート", stakeholder_seeds=seeds,
        )

    # フォールバック後は汎用エージェントが返る
    assert call_count == 2
    assert result["agents"][0]["name"] == "汎用エージェント"
