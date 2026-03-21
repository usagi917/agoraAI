"""エージェント選抜テスト: 多様性、関連度スコアリング"""

import pytest

from src.app.services.society.agent_selector import (
    select_agents,
    _extract_relevant_topics,
    _score_agent,
)


class TestExtractRelevantTopics:
    def test_economy_keywords(self):
        topics = _extract_relevant_topics("日本の経済成長と雇用問題について")
        assert "economy" in topics

    def test_technology_keywords(self):
        topics = _extract_relevant_topics("AI技術の社会的影響")
        assert "technology" in topics

    def test_multiple_topics(self):
        topics = _extract_relevant_topics("環境問題と経済のバランス")
        assert "environment" in topics
        assert "economy" in topics

    def test_no_match_returns_all(self):
        topics = _extract_relevant_topics("xyz completely unrelated topic")
        assert len(topics) == len(set(topics))
        assert len(topics) > 5  # all topics


class TestScoreAgent:
    def test_high_sensitivity_high_score(self):
        agent = {"shock_sensitivity": {"economy": 0.9, "technology": 0.8}}
        score = _score_agent(agent, ["economy", "technology"])
        assert score > 0.7

    def test_low_sensitivity_low_score(self):
        agent = {"shock_sensitivity": {"economy": 0.1, "technology": 0.1}}
        score = _score_agent(agent, ["economy", "technology"])
        assert score < 0.3

    def test_empty_topics(self):
        agent = {"shock_sensitivity": {"economy": 0.9}}
        score = _score_agent(agent, [])
        assert score == 0.5  # default


class TestSelectAgents:
    @pytest.fixture
    def sample_agents(self):
        agents = []
        for i in range(200):
            agents.append({
                "id": f"agent-{i}",
                "demographics": {
                    "region": ["北海道", "東北", "関東（都市部）", "関西（都市部）", "九州"][i % 5],
                    "age": 20 + (i % 60),
                    "education": ["high_school", "bachelor", "master"][i % 3],
                },
                "shock_sensitivity": {
                    "economy": (i % 10) / 10.0,
                    "technology": ((i + 3) % 10) / 10.0,
                    "environment": ((i + 5) % 10) / 10.0,
                },
            })
        return agents

    @pytest.mark.asyncio
    async def test_selects_correct_count(self, sample_agents):
        selected = await select_agents(sample_agents, "経済問題について", target_count=50)
        assert 50 <= len(selected) <= 60  # may include diversity additions

    @pytest.mark.asyncio
    async def test_selects_within_bounds(self, sample_agents):
        selected = await select_agents(sample_agents, "テスト", min_count=30, max_count=40, target_count=35)
        assert 30 <= len(selected) <= 45

    @pytest.mark.asyncio
    async def test_diversity_multiple_regions(self, sample_agents):
        selected = await select_agents(sample_agents, "経済問題", target_count=50)
        regions = {a["demographics"]["region"] for a in selected}
        assert len(regions) >= 4  # at least 4 of 5 regions

    @pytest.mark.asyncio
    async def test_handles_small_population(self):
        agents = [
            {"id": f"a-{i}", "demographics": {"region": "関東（都市部）"}, "shock_sensitivity": {}}
            for i in range(10)
        ]
        selected = await select_agents(agents, "テスト", target_count=100)
        assert len(selected) == 10  # can't exceed population

    @pytest.mark.asyncio
    async def test_unique_selections(self, sample_agents):
        selected = await select_agents(sample_agents, "経済問題", target_count=80)
        ids = [a["id"] for a in selected]
        assert len(ids) == len(set(ids))
