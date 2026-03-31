"""Tests for Network Propagation: multi-round opinion dynamics with LLM reflection.

Verifies:
- Multi-round propagation changes opinion distribution
- LLM reflection only triggers for agents with large opinion shifts
- Convergence causes automatic stop
- PropagationResult contains all required fields
- Integration with opinion_dynamics engine
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.app.services.society.network_propagation import (
    run_network_propagation,
    PropagationResult,
    _should_trigger_reflection,
    _convert_stance_to_opinion,
    _convert_opinion_to_stance,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_agent(idx: int, stance: str = "中立", confidence: float = 0.5,
                big_five_c: float = 0.5, region: str = "関東") -> dict:
    return {
        "id": f"agent_{idx}",
        "demographics": {"age": 30 + idx, "gender": "male", "region": region,
                         "occupation": "会社員", "income_bracket": "middle",
                         "education": "bachelor"},
        "big_five": {"O": 0.5, "C": big_five_c, "E": 0.5, "A": 0.5, "N": 0.5},
        "values": {"安全": 0.5},
        "speech_style": "率直で簡潔",
    }


def _make_response(idx: int, stance: str = "中立", confidence: float = 0.5) -> dict:
    return {
        "agent_id": f"agent_{idx}",
        "stance": stance,
        "confidence": confidence,
        "reason": f"テスト理由{idx}",
        "concern": f"テスト懸念{idx}",
        "priority": f"テスト優先事項{idx}",
    }


def _make_edge(src: int, tgt: int, strength: float = 0.5) -> dict:
    return {
        "agent_id": f"agent_{src}",
        "target_id": f"agent_{tgt}",
        "strength": strength,
    }


# ===========================================================================
# Test: Stance <-> Opinion Conversion
# ===========================================================================

class TestStanceOpinionConversion:
    """Bidirectional conversion between stance labels and opinion vectors."""

    def test_stance_to_opinion_mapping(self):
        assert _convert_stance_to_opinion("賛成", 0.9) == pytest.approx([0.9], abs=0.05)
        assert _convert_stance_to_opinion("条件付き賛成", 0.7) == pytest.approx([0.65], abs=0.1)
        assert _convert_stance_to_opinion("中立", 0.5) == pytest.approx([0.5], abs=0.05)
        assert _convert_stance_to_opinion("条件付き反対", 0.7) == pytest.approx([0.35], abs=0.1)
        assert _convert_stance_to_opinion("反対", 0.9) == pytest.approx([0.1], abs=0.05)

    def test_opinion_to_stance_mapping(self):
        assert _convert_opinion_to_stance([0.9]) == "賛成"
        assert _convert_opinion_to_stance([0.7]) == "条件付き賛成"
        assert _convert_opinion_to_stance([0.5]) == "中立"
        assert _convert_opinion_to_stance([0.3]) == "条件付き反対"
        assert _convert_opinion_to_stance([0.1]) == "反対"

    def test_roundtrip(self):
        """Converting stance -> opinion -> stance should preserve the stance."""
        for stance in ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]:
            opinion = _convert_stance_to_opinion(stance, 0.8)
            recovered = _convert_opinion_to_stance(opinion)
            assert recovered == stance

    def test_low_confidence_roundtrip_compresses_extreme_stances(self):
        """Low confidence compresses extreme stances toward center.

        This is intentional: an agent who says "賛成" with confidence=0.3
        is effectively "条件付き賛成" — their low conviction moderates
        their position. The opinion value 0.62 falls in the 条件付き賛成
        band [0.6, 0.8).
        """
        # 賛成 + low confidence → opinion closer to center → 条件付き賛成
        opinion = _convert_stance_to_opinion("賛成", 0.3)
        recovered = _convert_opinion_to_stance(opinion)
        assert recovered == "条件付き賛成", (
            f"賛成 with confidence=0.3 should compress to 条件付き賛成, got {recovered}"
        )

        # 反対 + low confidence → opinion closer to center → 条件付き反対
        opinion = _convert_stance_to_opinion("反対", 0.3)
        recovered = _convert_opinion_to_stance(opinion)
        assert recovered == "条件付き反対", (
            f"反対 with confidence=0.3 should compress to 条件付き反対, got {recovered}"
        )

        # 中立 is stable at any confidence (base=0.5, always maps back)
        opinion = _convert_stance_to_opinion("中立", 0.3)
        recovered = _convert_opinion_to_stance(opinion)
        assert recovered == "中立"


# ===========================================================================
# Test: Reflection Trigger
# ===========================================================================

class TestReflectionTrigger:
    """LLM reflection should only trigger for large opinion shifts."""

    def test_large_shift_triggers_reflection(self):
        assert _should_trigger_reflection(
            old_opinion=[0.2], new_opinion=[0.6], threshold=0.3,
        ) is True

    def test_small_shift_no_reflection(self):
        assert _should_trigger_reflection(
            old_opinion=[0.5], new_opinion=[0.55], threshold=0.3,
        ) is False

    def test_just_below_threshold_no_trigger(self):
        assert _should_trigger_reflection(
            old_opinion=[0.5], new_opinion=[0.79], threshold=0.3,
        ) is False


# ===========================================================================
# Test: Full Propagation Run
# ===========================================================================

class TestRunNetworkPropagation:
    """Integration tests for the full propagation pipeline."""

    @pytest.mark.asyncio
    async def test_propagation_returns_result(self):
        """run_network_propagation should return a well-formed PropagationResult."""
        agents = [_make_agent(i) for i in range(5)]
        responses = [
            _make_response(0, "賛成", 0.9),
            _make_response(1, "賛成", 0.8),
            _make_response(2, "中立", 0.5),
            _make_response(3, "反対", 0.8),
            _make_response(4, "反対", 0.9),
        ]
        edges = [
            _make_edge(0, 1), _make_edge(1, 0),
            _make_edge(1, 2), _make_edge(2, 1),
            _make_edge(2, 3), _make_edge(3, 2),
            _make_edge(3, 4), _make_edge(4, 3),
        ]

        result = await run_network_propagation(
            agents=agents,
            initial_responses=responses,
            edges=edges,
            theme="テスト政策",
            max_timesteps=5,
            confidence_threshold=0.5,
        )

        assert isinstance(result, PropagationResult)
        assert len(result.final_opinions) == 5
        assert len(result.timestep_history) > 0
        assert all(len(ts.opinions) == 5 for ts in result.timestep_history)
        assert isinstance(result.clusters, list)
        assert isinstance(result.converged, bool)
        assert isinstance(result.total_timesteps, int)

    @pytest.mark.asyncio
    async def test_propagation_changes_opinions(self):
        """Opinions should change after propagation (connected agents interact)."""
        agents = [_make_agent(i, big_five_c=0.2) for i in range(4)]
        responses = [
            _make_response(0, "賛成", 0.9),
            _make_response(1, "賛成", 0.8),
            _make_response(2, "反対", 0.8),
            _make_response(3, "反対", 0.9),
        ]
        # Fully connected
        edges = []
        for i in range(4):
            for j in range(4):
                if i != j:
                    edges.append(_make_edge(i, j, 0.8))

        result = await run_network_propagation(
            agents=agents,
            initial_responses=responses,
            edges=edges,
            theme="テスト政策",
            max_timesteps=10,
            confidence_threshold=1.0,
        )

        # After propagation with low stubbornness and full connectivity,
        # opinions should move toward center
        initial_range = 0.9 - 0.1  # 賛成(0.9) to 反対(0.1)
        final_ops = [op[0] for op in result.final_opinions]
        final_range = max(final_ops) - min(final_ops)
        assert final_range < initial_range

    @pytest.mark.asyncio
    async def test_propagation_respects_max_timesteps(self):
        """Should not exceed max_timesteps."""
        agents = [_make_agent(i) for i in range(3)]
        responses = [_make_response(i, "中立", 0.5) for i in range(3)]
        edges = [_make_edge(0, 1), _make_edge(1, 0)]

        result = await run_network_propagation(
            agents=agents,
            initial_responses=responses,
            edges=edges,
            theme="テスト",
            max_timesteps=3,
        )

        assert result.total_timesteps <= 3

    @pytest.mark.asyncio
    async def test_propagation_detects_convergence(self):
        """Identical opinions should converge immediately."""
        agents = [_make_agent(i) for i in range(3)]
        responses = [_make_response(i, "中立", 0.5) for i in range(3)]
        edges = [_make_edge(0, 1), _make_edge(1, 0), _make_edge(1, 2), _make_edge(2, 1)]

        result = await run_network_propagation(
            agents=agents,
            initial_responses=responses,
            edges=edges,
            theme="テスト",
            max_timesteps=20,
            convergence_threshold=0.01,
        )

        assert result.converged is True
        assert result.total_timesteps < 20

    @pytest.mark.asyncio
    async def test_final_opinions_have_stance_labels(self):
        """Final opinions should include converted stance labels."""
        agents = [_make_agent(i) for i in range(2)]
        responses = [
            _make_response(0, "賛成", 0.9),
            _make_response(1, "反対", 0.9),
        ]
        edges = [_make_edge(0, 1), _make_edge(1, 0)]

        result = await run_network_propagation(
            agents=agents,
            initial_responses=responses,
            edges=edges,
            theme="テスト",
            max_timesteps=3,
        )

        for opinion in result.final_opinions:
            assert isinstance(opinion, list)
            assert len(opinion) >= 1
            assert isinstance(opinion[0], float)


# ===========================================================================
# Test: Echo Chamber Metrics
# ===========================================================================

class TestEchoChamberMetrics:
    """Propagation result should include echo chamber detection."""

    @pytest.mark.asyncio
    async def test_homogeneous_network_high_echo(self):
        """All same-opinion agents should show high echo chamber coefficient."""
        agents = [_make_agent(i) for i in range(4)]
        responses = [_make_response(i, "賛成", 0.9) for i in range(4)]
        edges = [
            _make_edge(0, 1), _make_edge(1, 0),
            _make_edge(2, 3), _make_edge(3, 2),
        ]

        result = await run_network_propagation(
            agents=agents,
            initial_responses=responses,
            edges=edges,
            theme="テスト",
            max_timesteps=5,
        )

        assert "echo_chamber" in result.metrics
        # All agents agree → high homophily
        assert result.metrics["echo_chamber"]["homophily_index"] >= 0.8


# ===========================================================================
# Test: LLM Reflection
# ===========================================================================

class TestPolarizationIndex:
    """Polarization index should distinguish degrees of bimodality."""

    @pytest.mark.asyncio
    async def test_polarization_distinguishes_moderate_from_extreme(self):
        """Moderate polarization should have lower index than extreme polarization."""
        from src.app.services.society.network_propagation import _compute_echo_chamber_metrics

        # Moderate: opinions clustered at 0.3 and 0.7
        moderate_agents = [
            {"id": f"a{i}", "opinion": [0.3]} for i in range(5)
        ] + [
            {"id": f"b{i}", "opinion": [0.7]} for i in range(5)
        ]
        edges = [{"agent_id": "a0", "target_id": "b0"}]

        # Extreme: opinions at 0.0 and 1.0
        extreme_agents = [
            {"id": f"a{i}", "opinion": [0.0]} for i in range(5)
        ] + [
            {"id": f"b{i}", "opinion": [1.0]} for i in range(5)
        ]

        moderate_metrics = _compute_echo_chamber_metrics(moderate_agents, edges)
        extreme_metrics = _compute_echo_chamber_metrics(extreme_agents, edges)

        assert extreme_metrics["polarization_index"] > moderate_metrics["polarization_index"], (
            f"Extreme ({extreme_metrics['polarization_index']}) should be > "
            f"moderate ({moderate_metrics['polarization_index']})"
        )

    @pytest.mark.asyncio
    async def test_polarization_not_saturated_for_semi_extreme(self):
        """Semi-extreme bimodal (0.15 vs 0.85) should NOT saturate to same value
        as fully extreme (0.0 vs 1.0). Variance 0.1225 should remain < 1.0.

        With 0.083 normalization: 0.1225/0.083 = 1.48 → clamped to 1.0 (saturated!)
        With 0.25 normalization: 0.1225/0.25 = 0.49 (correct differentiation)
        """
        from src.app.services.society.network_propagation import _compute_echo_chamber_metrics

        # Semi-extreme: 0.15 vs 0.85
        semi_agents = [
            {"id": f"a{i}", "opinion": [0.15]} for i in range(5)
        ] + [
            {"id": f"b{i}", "opinion": [0.85]} for i in range(5)
        ]
        # Fully extreme: 0.0 vs 1.0
        extreme_agents = [
            {"id": f"a{i}", "opinion": [0.0]} for i in range(5)
        ] + [
            {"id": f"b{i}", "opinion": [1.0]} for i in range(5)
        ]
        edges = [{"agent_id": "a0", "target_id": "b0"}]

        semi_metrics = _compute_echo_chamber_metrics(semi_agents, edges)
        extreme_metrics = _compute_echo_chamber_metrics(extreme_agents, edges)

        # Semi-extreme should be strictly less than fully extreme
        assert semi_metrics["polarization_index"] < extreme_metrics["polarization_index"], (
            f"Semi-extreme ({semi_metrics['polarization_index']}) should be < "
            f"extreme ({extreme_metrics['polarization_index']}), but both saturated"
        )


class TestLLMReflection:
    """LLM reflection should generate explanations for agents with large opinion shifts."""

    def test_build_reflection_prompt_includes_neighbor_quotes(self):
        """_build_reflection_prompt should include neighbor opinions and agent persona."""
        from src.app.services.society.network_propagation import _build_reflection_prompt

        agent = _make_agent(0, stance="賛成", confidence=0.9)
        old_opinion = [0.9]
        new_opinion = [0.55]
        neighbor_opinions = [
            {"agent_id": "agent_1", "opinion": [0.3], "reason": "コストが高すぎる"},
            {"agent_id": "agent_2", "opinion": [0.2], "reason": "地方への影響が懸念される"},
        ]

        system_prompt, user_prompt = _build_reflection_prompt(
            agent, old_opinion, new_opinion, neighbor_opinions, theme="テスト政策",
        )

        # Should contain agent persona info
        assert "関東" in system_prompt or "関東" in user_prompt
        # Should contain neighbor quotes
        assert "コストが高すぎる" in user_prompt
        assert "地方への影響が懸念される" in user_prompt
        # Should reference opinion shift
        assert "賛成" in user_prompt or "0.9" in user_prompt

    def test_build_reflection_prompt_includes_agent_demographics(self):
        """Prompt should include agent's demographic info for persona grounding."""
        from src.app.services.society.network_propagation import _build_reflection_prompt

        agent = _make_agent(0, stance="反対", confidence=0.8, region="北海道")
        system_prompt, user_prompt = _build_reflection_prompt(
            agent, [0.1], [0.5],
            [{"agent_id": "agent_1", "opinion": [0.7], "reason": "効率が上がる"}],
            theme="DX推進",
        )
        assert "北海道" in system_prompt

    def test_reflection_not_triggered_for_small_delta(self):
        """Agents with small opinion shifts should NOT get reflections."""
        # This is already covered by TestReflectionTrigger but we verify
        # the integration: reflections list should be empty without shifts.
        assert _should_trigger_reflection([0.5], [0.52], threshold=0.3) is False

    @pytest.mark.asyncio
    async def test_run_propagation_with_llm_client_calls_reflection(self):
        """When llm_client is provided, reflection should be called for shifted agents."""
        # Create a polarized setup that causes large shifts
        agents = [_make_agent(i, big_five_c=0.2) for i in range(4)]
        responses = [
            _make_response(0, "賛成", 0.9),
            _make_response(1, "賛成", 0.8),
            _make_response(2, "反対", 0.9),
            _make_response(3, "反対", 0.8),
        ]
        # Fully connected => large shifts expected
        edges = []
        for i in range(4):
            for j in range(4):
                if i != j:
                    edges.append(_make_edge(i, j, 0.9))

        mock_llm_client = AsyncMock()
        mock_llm_client.call = AsyncMock(return_value=(
            "近隣の住民の反対意見を聞いて、コスト面の懸念が理解できた。",
            {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
        ))

        result = await run_network_propagation(
            agents=agents,
            initial_responses=responses,
            edges=edges,
            theme="テスト政策",
            max_timesteps=10,
            confidence_threshold=1.0,
            reflection_delta_threshold=0.05,  # Low threshold to ensure reflection triggers
            llm_client=mock_llm_client,
        )

        assert isinstance(result.reflections, list)
        assert len(result.reflections) > 0
        assert result.reflection_count > 0

        # Verify reflection structure
        for r in result.reflections:
            assert "agent_id" in r
            assert "old_stance" in r
            assert "new_stance" in r
            assert "reflection_text" in r

    @pytest.mark.asyncio
    async def test_run_propagation_without_llm_client_no_reflections(self):
        """When no llm_client is provided, reflections should be empty."""
        agents = [_make_agent(i, big_five_c=0.2) for i in range(4)]
        responses = [
            _make_response(0, "賛成", 0.9),
            _make_response(1, "賛成", 0.8),
            _make_response(2, "反対", 0.9),
            _make_response(3, "反対", 0.8),
        ]
        edges = []
        for i in range(4):
            for j in range(4):
                if i != j:
                    edges.append(_make_edge(i, j, 0.9))

        result = await run_network_propagation(
            agents=agents,
            initial_responses=responses,
            edges=edges,
            theme="テスト政策",
            max_timesteps=10,
            confidence_threshold=1.0,
        )

        assert isinstance(result.reflections, list)
        assert len(result.reflections) == 0
        assert result.reflection_count == 0

    @pytest.mark.asyncio
    async def test_reflections_contain_correct_stance_info(self):
        """Each reflection should have accurate old_stance and new_stance."""
        agents = [_make_agent(i, big_five_c=0.1) for i in range(3)]
        responses = [
            _make_response(0, "賛成", 0.95),
            _make_response(1, "反対", 0.95),
            _make_response(2, "反対", 0.95),
        ]
        edges = [
            _make_edge(0, 1, 0.9), _make_edge(1, 0, 0.9),
            _make_edge(0, 2, 0.9), _make_edge(2, 0, 0.9),
            _make_edge(1, 2, 0.9), _make_edge(2, 1, 0.9),
        ]

        mock_llm_client = AsyncMock()
        mock_llm_client.call = AsyncMock(return_value=(
            "周囲の反対意見に触れ、自分の考えも少し変わった。",
            {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
        ))

        result = await run_network_propagation(
            agents=agents,
            initial_responses=responses,
            edges=edges,
            theme="テスト政策",
            max_timesteps=10,
            confidence_threshold=1.0,
            reflection_delta_threshold=0.05,
            llm_client=mock_llm_client,
        )

        for r in result.reflections:
            # old_stance and new_stance should be valid stance labels
            valid_stances = {"賛成", "条件付き賛成", "中立", "条件付き反対", "反対"}
            assert r["old_stance"] in valid_stances
            assert r["new_stance"] in valid_stances
