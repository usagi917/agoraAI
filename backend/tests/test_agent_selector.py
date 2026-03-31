"""エージェント選抜テスト: 多様性、関連度スコアリング"""

import pytest

from src.app.services.society.agent_selector import (
    select_agents,
    _extract_relevant_topics,
    _score_agent,
    _age_bracket,
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


# ---------------------------------------------------------------------------
# Phase 1-3: 人口統計クォータのテスト
# ---------------------------------------------------------------------------

def _make_agent(i: int, age: int, region: str, gender: str) -> dict:
    """テスト用ダミーエージェントを生成するヘルパー。"""
    return {
        "id": f"agent-{i}",
        "demographics": {
            "age": age,
            "region": region,
            "gender": gender,
            "income_bracket": "lower_middle",
            "occupation": "会社員",
        },
        "shock_sensitivity": {
            "economy": (i % 10) / 10.0,
            "technology": ((i + 3) % 10) / 10.0,
            "health": ((i + 6) % 10) / 10.0,
        },
    }


@pytest.fixture
def demographic_agents():
    """年齢帯・地域・性別が均等に分布した200人のダミー集団。"""
    age_bracket_examples = [
        (20, "18-29"), (25, "18-29"),
        (35, "30-49"), (45, "30-49"),
        (55, "50-69"), (65, "50-69"),
        (72, "70+"),   (80, "70+"),
    ]
    regions = ["北海道", "東北", "関東（都市部）", "関西（都市部）", "九州", "中部", "中国"]
    genders = ["male", "female"]

    agents = []
    idx = 0
    for age, _ in age_bracket_examples:
        for region in regions:
            for gender in genders:
                agents.append(_make_agent(idx, age, region, gender))
                idx += 1
    # 200人を超えるように必要なら繰り返して確認しやすいサイズにする（112人→パディング）
    while len(agents) < 150:
        base = agents[idx % len(age_bracket_examples * len(regions) * len(genders))]
        agents.append(_make_agent(idx, base["demographics"]["age"],
                                   base["demographics"]["region"],
                                   base["demographics"]["gender"]))
        idx += 1
    return agents


class TestAgeBracket:
    """_age_bracket ヘルパー関数のユニットテスト。"""

    def test_18_29_lower_bound(self):
        assert _age_bracket(18) == "18-29"

    def test_18_29_upper_bound(self):
        assert _age_bracket(29) == "18-29"

    def test_30_49_lower_bound(self):
        assert _age_bracket(30) == "30-49"

    def test_30_49_upper_bound(self):
        assert _age_bracket(49) == "30-49"

    def test_50_69_lower_bound(self):
        assert _age_bracket(50) == "50-69"

    def test_50_69_upper_bound(self):
        assert _age_bracket(69) == "50-69"

    def test_70_plus_lower_bound(self):
        assert _age_bracket(70) == "70+"

    def test_70_plus_elderly(self):
        assert _age_bracket(90) == "70+"


class TestDemographicQuotas:
    """人口統計クォータを含む select_agents のテスト (Phase 1-3)。"""

    @pytest.mark.asyncio
    async def test_selection_covers_min_age_brackets(self, demographic_agents):
        """選出結果に最低3つの年齢帯を含む。"""
        selected = await select_agents(demographic_agents, "経済政策", target_count=50)
        brackets = {_age_bracket(a["demographics"]["age"]) for a in selected}
        assert len(brackets) >= 3, (
            f"Expected at least 3 age brackets, got {len(brackets)}: {brackets}"
        )

    @pytest.mark.asyncio
    async def test_selection_covers_min_regions(self, demographic_agents):
        """選出結果に最低3つの地域を含む。"""
        selected = await select_agents(demographic_agents, "経済政策", target_count=50)
        regions = {a["demographics"]["region"] for a in selected}
        assert len(regions) >= 3, (
            f"Expected at least 3 regions, got {len(regions)}: {regions}"
        )

    @pytest.mark.asyncio
    async def test_selection_covers_both_genders(self, demographic_agents):
        """選出結果に男女両方を含む。"""
        selected = await select_agents(demographic_agents, "経済政策", target_count=50)
        genders = {a["demographics"]["gender"] for a in selected}
        assert "male" in genders, "male agents should be included"
        assert "female" in genders, "female agents should be included"

    @pytest.mark.asyncio
    async def test_quota_fallback_when_insufficient(self):
        """母集団が小さい（20人）場合にエラーなく動作し、可能な限り多様性を維持する。"""
        small_population = [
            _make_agent(0,  22, "北海道",        "male"),
            _make_agent(1,  25, "東北",           "female"),
            _make_agent(2,  35, "関東（都市部）", "male"),
            _make_agent(3,  42, "関西（都市部）", "female"),
            _make_agent(4,  55, "九州",           "male"),
            _make_agent(5,  63, "中部",           "female"),
            _make_agent(6,  72, "中国",           "male"),
            _make_agent(7,  80, "北海道",         "female"),
            _make_agent(8,  28, "東北",           "male"),
            _make_agent(9,  38, "関東（都市部）", "female"),
            _make_agent(10, 48, "関西（都市部）", "male"),
            _make_agent(11, 58, "九州",           "female"),
            _make_agent(12, 68, "中部",           "male"),
            _make_agent(13, 75, "中国",           "female"),
            _make_agent(14, 23, "北海道",         "male"),
            _make_agent(15, 33, "東北",           "female"),
            _make_agent(16, 43, "関東（都市部）", "male"),
            _make_agent(17, 53, "関西（都市部）", "female"),
            _make_agent(18, 63, "九州",           "male"),
            _make_agent(19, 73, "中部",           "female"),
        ]
        # エラーなく動作し、全20人が返ってくる（target_count > population size）
        selected = await select_agents(small_population, "福祉政策", target_count=100)
        assert len(selected) == 20, f"Expected 20 agents, got {len(selected)}"

        # 多様性確認: 4年齢帯すべてと男女が揃う
        brackets = {_age_bracket(a["demographics"]["age"]) for a in selected}
        genders = {a["demographics"]["gender"] for a in selected}
        assert len(brackets) >= 3, f"Expected 3+ age brackets, got {brackets}"
        assert "male" in genders and "female" in genders
