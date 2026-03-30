"""代表者選出テスト"""

import pytest

from src.app.services.society.representative_selector import (
    select_representatives,
    _cluster_by_stance,
    _age_bracket,
)


class TestClusterByStance:
    def test_groups_correctly(self):
        agents = [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]
        responses = [
            {"stance": "賛成"},
            {"stance": "反対"},
            {"stance": "賛成"},
        ]
        clusters = _cluster_by_stance(agents, responses)
        assert len(clusters["賛成"]) == 2
        assert len(clusters["反対"]) == 1


class TestSelectRepresentatives:
    @pytest.mark.asyncio
    async def test_selects_citizens_and_experts(self):
        agents = [
            {"id": f"a{i}", "demographics": {"occupation": f"職業{i}", "age": 30 + i, "region": "関東（都市部）"}, "big_five": {}, "speech_style": "丁寧で慎重"}
            for i in range(20)
        ]
        responses = [
            {"stance": ["賛成", "反対", "中立", "条件付き賛成"][i % 4], "confidence": 0.5 + i * 0.02, "reason": f"理由{i}"}
            for i in range(20)
        ]
        participants = await select_representatives(agents, responses, max_citizen_reps=6, max_experts=4)

        citizen_count = sum(1 for p in participants if p["role"] == "citizen_representative")
        expert_count = sum(1 for p in participants if p["role"] == "expert")

        assert citizen_count <= 6
        assert expert_count <= 4
        assert len(participants) == citizen_count + expert_count

    @pytest.mark.asyncio
    async def test_experts_have_required_fields(self):
        agents = [{"id": "a1", "demographics": {"occupation": "test", "age": 30, "region": "test"}, "big_five": {}, "speech_style": "test"}]
        responses = [{"stance": "中立", "confidence": 0.5}]
        participants = await select_representatives(agents, responses, max_citizen_reps=1, max_experts=2)

        experts = [p for p in participants if p["role"] == "expert"]
        for e in experts:
            assert "expertise" in e
            assert "agent_profile" in e
            assert e["agent_profile"]["id"]

    @pytest.mark.asyncio
    async def test_citizens_from_multiple_stances(self):
        agents = [
            {"id": f"a{i}", "demographics": {"occupation": "test", "age": 30, "region": "test"}, "big_five": {}, "speech_style": "test"}
            for i in range(12)
        ]
        responses = [
            {"stance": ["賛成", "反対", "中立"][i % 3], "confidence": 0.5 + i * 0.03}
            for i in range(12)
        ]
        participants = await select_representatives(agents, responses, max_citizen_reps=6, max_experts=0)
        stances = {p.get("stance") for p in participants if p["role"] == "citizen_representative"}
        assert len(stances) >= 2


# ---------------------------------------------------------------------------
# Helper: _age_bracket
# ---------------------------------------------------------------------------

class TestAgeBracket:
    def test_18_to_29(self):
        assert _age_bracket(18) == "18-29"
        assert _age_bracket(25) == "18-29"
        assert _age_bracket(29) == "18-29"

    def test_30_to_49(self):
        assert _age_bracket(30) == "30-49"
        assert _age_bracket(40) == "30-49"
        assert _age_bracket(49) == "30-49"

    def test_50_to_69(self):
        assert _age_bracket(50) == "50-69"
        assert _age_bracket(60) == "50-69"
        assert _age_bracket(69) == "50-69"

    def test_70_plus(self):
        assert _age_bracket(70) == "70+"
        assert _age_bracket(85) == "70+"

    def test_boundary_30(self):
        assert _age_bracket(29) == "18-29"
        assert _age_bracket(30) == "30-49"

    def test_boundary_50(self):
        assert _age_bracket(49) == "30-49"
        assert _age_bracket(50) == "50-69"

    def test_boundary_70(self):
        assert _age_bracket(69) == "50-69"
        assert _age_bracket(70) == "70+"


# ---------------------------------------------------------------------------
# Diverse population fixture (30+ agents, 4 age brackets, 5+ regions, M/F)
# ---------------------------------------------------------------------------

def _make_diverse_population():
    """30人以上・4年齢帯・5地域・男女の母集団を生成する。"""
    stances = ["賛成", "反対", "中立", "条件付き賛成", "条件付き反対"]
    regions = ["北海道", "関東（都市部）", "関西（都市部）", "九州", "東北"]
    genders = ["male", "female"]

    # 年齢帯ごとに均等に割り当てる
    age_samples = [
        20, 22, 25, 28,          # 18-29 (4)
        32, 35, 40, 45, 48,      # 30-49 (5)
        52, 55, 60, 65, 68,      # 50-69 (5)
        72, 75, 80, 85,          # 70+   (4)
    ]
    # 18エージェントを追加して計30人にする
    extra_ages = [
        21, 24, 27,
        33, 38, 43,
        53, 58, 63,
        73, 78, 83,
    ]
    all_ages = age_samples + extra_ages  # 30人

    agents = []
    for i, age in enumerate(all_ages):
        agents.append({
            "id": f"div_{i}",
            "demographics": {
                "age": age,
                "gender": genders[i % 2],
                "region": regions[i % len(regions)],
                "occupation": f"職業{i}",
            },
            "big_five": {},
            "speech_style": "普通",
        })

    responses = [
        {
            "stance": stances[i % len(stances)],
            "confidence": 0.4 + (i % 6) * 0.1,
        }
        for i in range(len(agents))
    ]
    return agents, responses


class TestDiversityGuarantees:
    """市民代表選出の多様性制約テスト（Phase 1-4）"""

    @pytest.mark.asyncio
    async def test_citizens_span_age_brackets(self):
        """市民代表が最低3つの年齢帯をカバーすること。"""
        agents, responses = _make_diverse_population()
        participants = await select_representatives(
            agents, responses, max_citizen_reps=6, max_experts=0
        )
        citizens = [p for p in participants if p["role"] == "citizen_representative"]
        brackets = {
            _age_bracket(p["agent_profile"]["demographics"]["age"])
            for p in citizens
        }
        assert len(brackets) >= 3, (
            f"Expected >=3 age brackets, got {len(brackets)}: {brackets}"
        )

    @pytest.mark.asyncio
    async def test_citizens_span_regions(self):
        """市民代表が最低3つの地域をカバーすること。"""
        agents, responses = _make_diverse_population()
        participants = await select_representatives(
            agents, responses, max_citizen_reps=6, max_experts=0
        )
        citizens = [p for p in participants if p["role"] == "citizen_representative"]
        regions = {p["agent_profile"]["demographics"]["region"] for p in citizens}
        assert len(regions) >= 3, (
            f"Expected >=3 regions, got {len(regions)}: {regions}"
        )

    @pytest.mark.asyncio
    async def test_citizens_include_both_genders(self):
        """市民代表に男女両方が含まれること。"""
        agents, responses = _make_diverse_population()
        participants = await select_representatives(
            agents, responses, max_citizen_reps=6, max_experts=0
        )
        citizens = [p for p in participants if p["role"] == "citizen_representative"]
        genders = {p["agent_profile"]["demographics"]["gender"] for p in citizens}
        assert "male" in genders, "No male citizen representative selected"
        assert "female" in genders, "No female citizen representative selected"

    @pytest.mark.asyncio
    async def test_diversity_fallback(self):
        """母集団が小さく（10人・同年齢帯・同地域）多様性制約を完全充足できない場合でも
        エラーなく動作し、可能な範囲で代表を返すこと。"""
        agents = [
            {
                "id": f"small_{i}",
                "demographics": {
                    "age": 30 + i,   # 全員 30-49 帯
                    "gender": "male", # 全員 male
                    "region": "関東（都市部）",  # 全員同地域
                    "occupation": f"職業{i}",
                },
                "big_five": {},
                "speech_style": "普通",
            }
            for i in range(10)
        ]
        responses = [
            {"stance": ["賛成", "反対"][i % 2], "confidence": 0.5 + i * 0.03}
            for i in range(10)
        ]
        # エラーなく実行できること
        participants = await select_representatives(
            agents, responses, max_citizen_reps=6, max_experts=0
        )
        citizens = [p for p in participants if p["role"] == "citizen_representative"]
        assert len(citizens) >= 1, "Should return at least 1 citizen even on fallback"
        assert len(citizens) <= 6, "Should not exceed max_citizen_reps"
