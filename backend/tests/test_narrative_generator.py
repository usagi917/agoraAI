"""TDD tests for narrative_generator.py — Phase 2-3: methodology section."""

import pytest

from src.app.services.society.narrative_generator import generate_narrative


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

dummy_provenance = {
    "methodology": {
        "framework": "Modified Fishkin Deliberative Polling",
        "citation": "Fishkin, J.S. (2009)...",
        "population_sampling": "Census-weighted stratified random sampling",
        "deliberation_protocol": "3-round structured discussion",
        "aggregation_method": "Post-stratification weighted counting with bootstrap CIs",
    },
    "data_sources": [
        {"name": "2020 国勢調査", "used_for": "人口統計分布"},
    ],
    "parameters": {
        "population_size": 10000,
        "selected_sample_size": 100,
        "effective_sample_size": 87.5,
    },
    "quality_metrics": {
        "diversity_index": 0.82,
    },
    "limitations": [
        "LLMが生成した意見は実際の人間の選好を反映するものではない",
    ],
}

minimal_agents = [
    {"id": "a1", "agent_index": 0, "demographics": {"occupation": "会社員", "age": 35, "region": "東京"}},
]
minimal_responses = [
    {"stance": "賛成", "confidence": 0.8, "reason": "経済的メリットが大きい"},
]
minimal_synthesis = {
    "overall_assessment": "概ね賛成の傾向がある",
    "consensus_points": ["経済効果への期待"],
    "disagreement_points": [],
    "recommendations": [],
    "key_insights": [],
    "scenarios": [],
    "stance_shifts": [],
}
minimal_aggregation = {
    "stance_distribution": {"賛成": 0.8, "反対": 0.2},
    "total_respondents": 1,
    "average_confidence": 0.8,
}
minimal_demographic_analysis = {"by_age": {}, "by_region": {}}


def _call_generate(provenance=None):
    """Helper to call generate_narrative with minimal valid inputs."""
    return generate_narrative(
        agents=minimal_agents,
        responses=minimal_responses,
        synthesis=minimal_synthesis,
        aggregation=minimal_aggregation,
        demographic_analysis=minimal_demographic_analysis,
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# Methodology section tests
# ---------------------------------------------------------------------------


def test_narrative_includes_methodology():
    """generate_narrative の返り値に methodology_section キーが存在し、空でない文字列。"""
    result = _call_generate(provenance=dummy_provenance)
    assert "methodology_section" in result, "methodology_section キーが返り値に存在しない"
    section = result["methodology_section"]
    assert isinstance(section, str), f"methodology_section は str であるべきだが {type(section)} が返った"
    assert len(section.strip()) > 0, "methodology_section が空文字列"


def test_methodology_mentions_sample_size():
    """methodology_section に有効標本数情報が含まれる。"""
    result = _call_generate(provenance=dummy_provenance)
    section = result["methodology_section"]
    has_japanese = "有効標本数" in section
    has_english = "effective_sample_size" in section
    assert has_japanese or has_english, (
        "methodology_section に '有効標本数' または 'effective_sample_size' が含まれていない\n"
        f"実際の内容:\n{section}"
    )


def test_methodology_mentions_confidence_interval():
    """methodology_section に信頼区間の記載が含まれる。"""
    result = _call_generate(provenance=dummy_provenance)
    section = result["methodology_section"]
    assert "信頼区間" in section, (
        "methodology_section に '信頼区間' が含まれていない\n"
        f"実際の内容:\n{section}"
    )


def test_methodology_mentions_fishkin():
    """methodology_section に Fishkin への言及が含まれる。"""
    result = _call_generate(provenance=dummy_provenance)
    section = result["methodology_section"]
    assert "Fishkin" in section, (
        "methodology_section に 'Fishkin' が含まれていない\n"
        f"実際の内容:\n{section}"
    )


def test_methodology_mentions_limitations():
    """methodology_section に制約事項の記載が含まれる。"""
    result = _call_generate(provenance=dummy_provenance)
    section = result["methodology_section"]
    has_seiyaku = "制約" in section
    has_genkai = "限界" in section
    assert has_seiyaku or has_genkai, (
        "methodology_section に '制約' または '限界' が含まれていない\n"
        f"実際の内容:\n{section}"
    )


def test_narrative_without_provenance_has_no_methodology():
    """provenance=None で呼ぶと methodology_section が None になる。"""
    result = _call_generate(provenance=None)
    assert "methodology_section" in result, "methodology_section キーが返り値に存在しない"
    assert result["methodology_section"] is None, (
        f"provenance=None のとき methodology_section は None であるべきだが "
        f"{result['methodology_section']!r} が返った"
    )


# ---------------------------------------------------------------------------
# Backward-compatibility: existing keys must still be present
# ---------------------------------------------------------------------------


def test_existing_keys_unchanged_when_provenance_given():
    """provenance を渡しても既存キーが全て保持される。"""
    result = _call_generate(provenance=dummy_provenance)
    required_keys = [
        "executive_summary",
        "key_findings",
        "consensus_areas",
        "controversy_areas",
        "recommendations",
        "stance_shifts",
    ]
    for key in required_keys:
        assert key in result, f"既存キー '{key}' が返り値に存在しない"


def test_existing_keys_unchanged_without_provenance():
    """provenance=None でも既存キーが全て保持される。"""
    result = _call_generate(provenance=None)
    required_keys = [
        "executive_summary",
        "key_findings",
        "consensus_areas",
        "controversy_areas",
        "recommendations",
        "stance_shifts",
    ]
    for key in required_keys:
        assert key in result, f"既存キー '{key}' が返り値に存在しない (provenance=None)"
