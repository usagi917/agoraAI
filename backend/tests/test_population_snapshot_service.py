"""PopulationSnapshot サービスのテスト (Stream B)"""

import pytest

from src.app.models.population import Population
from src.app.services.population_snapshot_service import (
    create_snapshot,
    restore_from_snapshot,
)


def _make_mock_agents(count: int = 3) -> list[dict]:
    """テスト用のモックエージェントデータを生成する。"""
    return [
        {
            "id": f"agent-{i}",
            "population_id": "pop-test",
            "agent_index": i,
            "demographics": {
                "age": 30 + i,
                "gender": "male",
                "occupation": "エンジニア",
                "region": "関東（都市部）",
                "income_bracket": "upper_middle",
                "education": "bachelor",
            },
            "big_five": {
                "O": 0.7 + i * 0.01,
                "C": 0.6,
                "E": 0.5,
                "A": 0.4,
                "N": 0.3,
            },
            "values": {"innovation": 0.4, "efficiency": 0.3, "freedom": 0.3},
            "life_event": "昇進した",
            "contradiction": "計画的で慎重だが変化を求める気持ちもある",
            "information_source": "Yahoo!ニュース",
            "local_context": "関東（都市部）在住のエンジニア",
            "hidden_motivation": "さらなる資産形成と事業拡大の機会を狙っている",
            "speech_style": "分析的で論理的",
            "shock_sensitivity": {
                "economy": 0.8,
                "technology": 0.9,
                "environment": 0.2,
                "health": 0.3,
                "education": 0.1,
                "security": 0.5,
                "immigration": 0.1,
                "taxation": 0.7,
                "welfare": 0.2,
                "energy": 0.3,
            },
            "llm_backend": "openai",
            "memory_summary": "関東（都市部）でエンジニアとして働く30歳。昇進した",
        }
        for i in range(count)
    ]


class TestCreateSnapshot:
    @pytest.mark.asyncio
    async def test_create_snapshot(self, db_session):
        pop = Population(agent_count=3)
        db_session.add(pop)
        await db_session.commit()

        agents = _make_mock_agents(3)
        snapshot = await create_snapshot(db_session, pop.id, agents, seed=42)

        assert snapshot.id is not None
        assert snapshot.population_id == pop.id
        assert snapshot.agent_profiles_json == agents
        assert snapshot.relationships_json == {}
        assert snapshot.initial_beliefs_json == {}
        assert snapshot.seed == 42
        assert snapshot.created_at is not None


class TestRestoreFromSnapshot:
    @pytest.mark.asyncio
    async def test_restore_from_snapshot(self, db_session):
        pop = Population(agent_count=3)
        db_session.add(pop)
        await db_session.commit()

        agents = _make_mock_agents(3)
        snapshot = await create_snapshot(db_session, pop.id, agents, seed=42)

        restored = await restore_from_snapshot(db_session, snapshot.id)
        assert restored == agents
        assert len(restored) == 3

    @pytest.mark.asyncio
    async def test_restore_from_snapshot_not_found(self, db_session):
        with pytest.raises(ValueError, match="Snapshot not found"):
            await restore_from_snapshot(db_session, "nonexistent-id")


class TestSnapshotPreservesAllFields:
    @pytest.mark.asyncio
    async def test_snapshot_preserves_all_fields(self, db_session):
        """全エージェントフィールドがシリアライズのラウンドトリップで保持されることを検証。"""
        pop = Population(agent_count=1)
        db_session.add(pop)
        await db_session.commit()

        agents = _make_mock_agents(1)
        original = agents[0]
        snapshot = await create_snapshot(db_session, pop.id, agents, seed=99)

        restored = await restore_from_snapshot(db_session, snapshot.id)
        roundtripped = restored[0]

        # 全フィールドが一致することを確認
        assert roundtripped["id"] == original["id"]
        assert roundtripped["population_id"] == original["population_id"]
        assert roundtripped["agent_index"] == original["agent_index"]
        assert roundtripped["demographics"] == original["demographics"]
        assert roundtripped["big_five"] == original["big_five"]
        assert roundtripped["values"] == original["values"]
        assert roundtripped["life_event"] == original["life_event"]
        assert roundtripped["contradiction"] == original["contradiction"]
        assert roundtripped["information_source"] == original["information_source"]
        assert roundtripped["local_context"] == original["local_context"]
        assert roundtripped["hidden_motivation"] == original["hidden_motivation"]
        assert roundtripped["speech_style"] == original["speech_style"]
        assert roundtripped["shock_sensitivity"] == original["shock_sensitivity"]
        assert roundtripped["llm_backend"] == original["llm_backend"]
        assert roundtripped["memory_summary"] == original["memory_summary"]


class TestSnapshotWithSeed:
    @pytest.mark.asyncio
    async def test_snapshot_with_seed(self, db_session):
        """seed が正しく保存・取得されることを検証。"""
        pop = Population(agent_count=2)
        db_session.add(pop)
        await db_session.commit()

        agents = _make_mock_agents(2)

        snapshot_a = await create_snapshot(db_session, pop.id, agents, seed=123)
        snapshot_b = await create_snapshot(db_session, pop.id, agents, seed=456)

        assert snapshot_a.seed == 123
        assert snapshot_b.seed == 456

        # DB から再取得して確認
        from src.app.models.population_snapshot import PopulationSnapshot

        fetched_a = await db_session.get(PopulationSnapshot, snapshot_a.id)
        fetched_b = await db_session.get(PopulationSnapshot, snapshot_b.id)
        assert fetched_a.seed == 123
        assert fetched_b.seed == 456
