"""Tests for Output Quality improvements:
1. Activation-Meeting gap explanation
2. Qualitative conflict axis analysis with clusters
3. Meeting counter-argument structure
"""

import pytest

from src.app.services.society.output_validator import (
    explain_activation_meeting_gap,
)
from src.app.services.society.narrative_generator import (
    _build_controversy_areas_v2,
)


# ===========================================================================
# Fixtures
# ===========================================================================

def _sample_aggregation(pro_ratio=0.71, con_ratio=0.16, oppose_ratio=0.12, neutral_ratio=0.01):
    return {
        "stance_distribution": {
            "条件付き賛成": pro_ratio,
            "条件付き反対": con_ratio,
            "反対": oppose_ratio,
            "中立": neutral_ratio,
        },
        "average_confidence": 0.63,
        "total_respondents": 99,
        "effective_sample_size": 85.0,
    }


def _sample_synthesis(judgment_score=0.52, recommendation="条件付きGo"):
    return {
        "judgment_score": judgment_score,
        "recommendation": recommendation,
        "overall_assessment": "条件付き賛成が支配的だが、財源安定性への懸念が大きい",
        "consensus_points": ["教育機会の平等は共通目標"],
        "disagreement_points": [
            {"topic": "財源の構成", "positions": ["一本化税", "多元的財源"]},
            {"topic": "高齢者負担", "positions": ["軽減必要", "全世代負担"]},
        ],
    }


def _sample_propagation_result():
    return {
        "converged": True,
        "total_timesteps": 12,
        "clusters": [
            {"label": 0, "size": 60, "centroid": [0.65], "member_ids": [f"a{i}" for i in range(60)]},
            {"label": 1, "size": 30, "centroid": [0.25], "member_ids": [f"a{i}" for i in range(60, 90)]},
            {"label": 2, "size": 9, "centroid": [0.50], "member_ids": [f"a{i}" for i in range(90, 99)]},
        ],
        "echo_chamber": {"homophily_index": 0.72, "polarization_index": 0.45},
        "timestep_history": [
            {"timestep": 0, "opinion_distribution": {"条件付き賛成": 0.55, "反対": 0.20, "条件付き反対": 0.20, "中立": 0.05}},
            {"timestep": 12, "opinion_distribution": {"条件付き賛成": 0.71, "反対": 0.12, "条件付き反対": 0.16, "中立": 0.01}},
        ],
    }


def _sample_meeting_participants():
    return [
        {"display_name": "佐藤", "stance": "条件付き反対", "role": "citizen_representative"},
        {"display_name": "山本", "stance": "条件付き賛成", "role": "citizen_representative"},
        {"display_name": "小林", "stance": "条件付き反対", "role": "citizen_representative"},
        {"display_name": "中村", "stance": "反対", "role": "citizen_representative"},
        {"display_name": "北川", "stance": "反対", "role": "citizen_representative"},
        {"display_name": "田中", "stance": "条件付き賛成", "role": "citizen_representative"},
        {"display_name": "藤原", "stance": "", "role": "expert", "expertise": "economist"},
        {"display_name": "森下", "stance": "", "role": "expert", "expertise": "education_expert"},
        {"display_name": "木村", "stance": "", "role": "expert", "expertise": "policy_analyst"},
        {"display_name": "石井", "stance": "", "role": "expert", "expertise": "sociologist"},
    ]


# ===========================================================================
# Test: explain_activation_meeting_gap
# ===========================================================================

class TestExplainActivationMeetingGap:
    """Gap explanation should decompose why activation and meeting diverge."""

    def test_returns_gap_description(self):
        result = explain_activation_meeting_gap(
            aggregation=_sample_aggregation(),
            synthesis=_sample_synthesis(),
        )
        assert "gap_description" in result
        assert isinstance(result["gap_description"], str)
        assert len(result["gap_description"]) > 0

    def test_returns_factors(self):
        result = explain_activation_meeting_gap(
            aggregation=_sample_aggregation(),
            synthesis=_sample_synthesis(),
        )
        assert "factors" in result
        assert isinstance(result["factors"], list)
        assert len(result["factors"]) > 0
        for factor in result["factors"]:
            assert "factor" in factor
            assert "description" in factor

    def test_detects_meeting_composition_bias(self):
        """When meeting has more 反対 members than activation proportion, flag it."""
        result = explain_activation_meeting_gap(
            aggregation=_sample_aggregation(),
            synthesis=_sample_synthesis(),
            meeting_participants=_sample_meeting_participants(),
        )
        factor_names = [f["factor"] for f in result["factors"]]
        assert "meeting_composition_bias" in factor_names

    def test_no_gap_when_aligned(self):
        """When activation and meeting agree, gap should be minimal."""
        result = explain_activation_meeting_gap(
            aggregation=_sample_aggregation(pro_ratio=0.8),
            synthesis=_sample_synthesis(judgment_score=0.82),
        )
        assert result.get("gap_severity", "none") in ("none", "low")

    def test_includes_propagation_shift_when_provided(self):
        """When propagation data is available, include opinion shift analysis."""
        result = explain_activation_meeting_gap(
            aggregation=_sample_aggregation(),
            synthesis=_sample_synthesis(),
            propagation_data=_sample_propagation_result(),
        )
        factor_names = [f["factor"] for f in result["factors"]]
        assert "network_propagation_shift" in factor_names

    def test_includes_cluster_information(self):
        """When propagation produced clusters, explain their impact."""
        result = explain_activation_meeting_gap(
            aggregation=_sample_aggregation(),
            synthesis=_sample_synthesis(),
            propagation_data=_sample_propagation_result(),
        )
        factor_names = [f["factor"] for f in result["factors"]]
        assert "opinion_clustering" in factor_names

    def test_gap_severity_classification(self):
        """Gap should be classified as none/low/medium/high."""
        # Large gap
        result = explain_activation_meeting_gap(
            aggregation=_sample_aggregation(pro_ratio=0.85),
            synthesis=_sample_synthesis(judgment_score=0.40),
        )
        assert result["gap_severity"] in ("medium", "high")


# ===========================================================================
# Test: _build_controversy_areas_v2
# ===========================================================================

class TestBuildControversyAreasV2:
    """Controversy areas should include cluster-based qualitative analysis."""

    def _make_agents_and_responses(self, n=20):
        agents = []
        responses = []
        stances = ["賛成", "条件付き賛成", "条件付き反対", "反対"]
        for i in range(n):
            stance = stances[i % len(stances)]
            agents.append({
                "id": f"agent_{i}",
                "agent_index": i,
                "demographics": {
                    "age": 20 + i * 2,
                    "gender": "male" if i % 2 == 0 else "female",
                    "region": "関東" if i < 10 else "関西",
                    "occupation": "会社員",
                },
            })
            responses.append({
                "stance": stance,
                "confidence": 0.5 + (i % 5) * 0.1,
                "reason": f"これは{stance}の理由です。具体的な根拠として数値データ{i*100}を示します。",
                "concern": f"懸念事項{i}",
                "opinion_vector": [0.2 + i * 0.03],
            })
        return agents, responses

    def test_returns_controversy_list(self):
        agents, responses = self._make_agents_and_responses()
        synthesis = _sample_synthesis()
        demo = {"by_age": {}, "by_region": {}}

        result = _build_controversy_areas_v2(
            synthesis, agents, responses, demo,
        )
        assert isinstance(result, list)
        assert len(result) > 0

    def test_each_controversy_has_cluster_info(self):
        agents, responses = self._make_agents_and_responses()
        synthesis = _sample_synthesis()
        demo = {"by_age": {}, "by_region": {}}
        clusters = [
            {"label": 0, "size": 12, "centroid": [0.7], "member_ids": [f"agent_{i}" for i in range(12)]},
            {"label": 1, "size": 8, "centroid": [0.3], "member_ids": [f"agent_{i}" for i in range(12, 20)]},
        ]

        result = _build_controversy_areas_v2(
            synthesis, agents, responses, demo, clusters=clusters,
        )

        for area in result:
            assert "cluster_analysis" in area
            assert isinstance(area["cluster_analysis"], dict)

    def test_each_controversy_has_confidence_breakdown(self):
        agents, responses = self._make_agents_and_responses()
        synthesis = _sample_synthesis()
        demo = {"by_age": {}, "by_region": {}}

        result = _build_controversy_areas_v2(
            synthesis, agents, responses, demo,
        )

        for area in result:
            assert "conviction_strength" in area

    def test_each_controversy_has_supporting_stances(self):
        agents, responses = self._make_agents_and_responses()
        synthesis = _sample_synthesis()
        demo = {"by_age": {}, "by_region": {}}

        result = _build_controversy_areas_v2(
            synthesis, agents, responses, demo,
        )

        for area in result:
            assert "supporting_stances" in area
            assert isinstance(area["supporting_stances"], list)

    def test_bridge_agents_identified_when_clusters_provided(self):
        """Bridge agents = those near cluster boundaries or who shifted stance."""
        agents, responses = self._make_agents_and_responses()
        synthesis = _sample_synthesis()
        demo = {"by_age": {}, "by_region": {}}
        clusters = [
            {"label": 0, "size": 12, "centroid": [0.7], "member_ids": [f"agent_{i}" for i in range(12)]},
            {"label": 1, "size": 8, "centroid": [0.3], "member_ids": [f"agent_{i}" for i in range(12, 20)]},
        ]

        result = _build_controversy_areas_v2(
            synthesis, agents, responses, demo, clusters=clusters,
        )

        for area in result:
            assert "bridge_agents" in area

    def test_fallback_when_no_disagreement_points(self):
        agents, responses = self._make_agents_and_responses()
        synthesis = {"disagreement_points": []}
        demo = {"by_age": {}, "by_region": {}}

        result = _build_controversy_areas_v2(
            synthesis, agents, responses, demo,
        )
        assert result == []
