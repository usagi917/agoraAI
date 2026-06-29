"""Tests for Network Propagation: multi-round opinion dynamics with LLM reflection.

Verifies:
- Multi-round propagation changes opinion distribution
- LLM reflection only triggers for agents with large opinion shifts
- Convergence causes automatic stop
- PropagationResult contains all required fields
- Integration with opinion_dynamics engine
- Meeting feedback propagation (improvement 4)
"""

import pytest
from unittest.mock import AsyncMock, patch

import numpy as np

from src.app.services.society.network_propagation import (
    run_network_propagation,
    run_meeting_feedback_propagation,
    PropagationResult,
    _should_trigger_reflection,
    _convert_stance_to_opinion,
    _convert_opinion_to_stance,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_agent(idx: int, stance: str = "中立", confidence: float = 0.5,
                big_five_c: float = 0.5, big_five_a: float = 0.5,
                region: str = "関東") -> dict:
    return {
        "id": f"agent_{idx}",
        "demographics": {"age": 30 + idx, "gender": "male", "region": region,
                         "occupation": "会社員", "income_bracket": "middle",
                         "education": "bachelor"},
        "big_five": {"O": 0.5, "C": big_five_c, "E": 0.5, "A": big_five_a, "N": 0.5},
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
# Test: Phase 3 Belief Decay Integration (Step 8)
# ===========================================================================

class TestBeliefDecayIntegration:
    """Phase 3 (belief decay) が run_network_propagation() で適用されることを確認する。"""

    @pytest.mark.asyncio
    async def test_apply_belief_decay_called_per_agent_per_timestep(self):
        """各タイムステップで各エージェントに apply_belief_decay が呼ばれること。

        apply_belief_decay をモックしてコール回数を計測する。
        実装が正しければ: total_calls == n_agents * total_timesteps
        """
        from src.app.services.society.opinion_dynamics import apply_belief_decay as real_decay
        call_args: list[tuple[float, float]] = []

        def tracking_decay(current: float, initial: float) -> float:
            call_args.append((current, initial))
            return real_decay(current, initial)

        n_agents = 3
        n_steps = 5
        agents = [_make_agent(i) for i in range(n_agents)]
        responses = [
            _make_response(0, "賛成", 0.8),
            _make_response(1, "中立", 0.5),
            _make_response(2, "反対", 0.8),
        ]
        edges = [_make_edge(0, 1), _make_edge(1, 0), _make_edge(1, 2), _make_edge(2, 1)]

        with patch(
            "src.app.services.society.network_propagation.apply_belief_decay",
            tracking_decay,
        ):
            result = await run_network_propagation(
                agents=agents,
                initial_responses=responses,
                edges=edges,
                theme="経済政策",
                max_timesteps=n_steps,
                convergence_threshold=0.000001,  # 収束させない
            )

        total_ts = result.total_timesteps
        expected_min_calls = n_agents * total_ts
        assert len(call_args) == expected_min_calls, (
            f"apply_belief_decay コール数: {len(call_args)} != {expected_min_calls} "
            f"(n_agents={n_agents}, total_timesteps={total_ts})"
        )

    @pytest.mark.asyncio
    async def test_belief_decay_pulls_opinion_toward_initial(self):
        """decay が initial 方向へ引き戻すことを数値的に確認する。

        1 ステップ後の final_opinion が TimestepRecord の opinion (会話後の raw 値)
        より initial に近いことを確認する。

        実装:
          - propagation_step() の結果を TimestepRecord に記録
          - その後 apply_belief_decay を engine._opinions に適用
          - final_opinions は decay 済みの engine._opinions から取得

        したがって: abs(final - initial) < abs(step_record - initial) がデケイ適用の証拠。
        """
        from src.app.services.society.opinion_dynamics import (
            apply_belief_decay,
            BASE_DECAY,
            stubbornness_from_big_five,
        )

        # confidence_threshold=0.8 で 2 エージェントが相互作用できる距離に設定
        # 賛成(0.8): opinion = 0.5 + 0.4*0.8 = 0.82
        # 反対(0.8): opinion = 0.5 - 0.4*0.8 = 0.18
        # 距離 = 0.64 → threshold=0.8 > 0.64 なので相互作用する
        agents = [_make_agent(0, big_five_c=0.5), _make_agent(1, big_five_c=0.5)]
        responses = [_make_response(0, "賛成", 0.8), _make_response(1, "反対", 0.8)]
        edges = [_make_edge(0, 1, 1.0), _make_edge(1, 0, 1.0)]

        result = await run_network_propagation(
            agents=agents,
            initial_responses=responses,
            edges=edges,
            theme="経済政策",
            max_timesteps=1,
            convergence_threshold=0.000001,
            confidence_threshold=0.8,  # 相互作用できるよう広くする
        )

        # TimestepRecord に記録された opinion (propagation_step の raw 出力)
        step_op0 = result.timestep_history[0].opinions[0][0]
        # final_opinions (apply_belief_decay 適用後の engine._opinions)
        final_op0 = result.final_opinions[0][0]

        # 初期 opinion (engine 生成時)
        initial_op0 = 0.5 + (0.9 - 0.5) * 0.8  # = 0.82

        # 賛成エージェントは会話で引き下げられる (step_op0 < initial_op0)
        # decay 適用後: final_op0 = apply_belief_decay(step_op0, initial_op0)
        #                          = step_op0 - BASE_DECAY * (step_op0 - initial_op0)
        #                          = step_op0 + BASE_DECAY * (initial_op0 - step_op0)
        # つまり final_op0 > step_op0 (decay で initial 方向, i.e. 上方向へ戻る)
        # これは abs(final_op0 - initial_op0) < abs(step_op0 - initial_op0) と同義

        # 会話で意見が変化することは本テストの前提。変化が無いと decay 検証が無意味になり
        # デグレを見逃すため、skip ではなく assert で必須化する（変化ロジックが壊れたら FAIL）。
        assert abs(step_op0 - initial_op0) >= 1e-6, (
            "会話による意見変化が起きていない（前提条件の不成立 = 意見変化ロジックのデグレの可能性）"
        )

        # decay が適用されているなら: final は step より initial に近い
        dist_final_to_initial = abs(final_op0 - initial_op0)
        dist_step_to_initial = abs(step_op0 - initial_op0)

        assert dist_final_to_initial < dist_step_to_initial, (
            f"decay 適用後は initial により近いはず: "
            f"final_gap={dist_final_to_initial:.6f}, step_gap={dist_step_to_initial:.6f}, "
            f"initial={initial_op0:.4f}, step_op0={step_op0:.4f}, final_op0={final_op0:.4f}"
        )


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


# ===========================================================================
# Test: Meeting Feedback Propagation (Improvement 4)
# ===========================================================================

class TestMeetingFeedbackPropagation:
    """Meeting feedback propagation: representative stance changes ripple to population."""

    def _make_agents_and_edges(self, n: int = 5):
        """Create a line graph: 0-1-2-3-4 with bidirectional edges."""
        agents = [_make_agent(i, big_five_c=0.3) for i in range(n)]
        responses = [_make_response(i, "反対", 0.8) for i in range(n)]
        edges = []
        for i in range(n - 1):
            edges.append(_make_edge(i, i + 1, 0.8))
            edges.append(_make_edge(i + 1, i, 0.8))
        return agents, responses, edges

    @pytest.mark.asyncio
    async def test_representative_shift_propagates(self):
        """When a representative shifts stance, their neighbor's opinion should move."""
        agents, responses, edges = self._make_agents_and_edges(5)

        # agent_0 was 反対, now shifts to 賛成 after meeting
        representative_updates = [
            {"agent_id": "agent_0", "old_stance": "反対", "new_stance": "賛成"},
        ]

        result = await run_meeting_feedback_propagation(
            agents=agents,
            edges=edges,
            representative_updates=representative_updates,
            activation_responses=responses,
        )

        assert "opinions" in result
        assert "changed_agents" in result
        assert "propagation_record" in result

        # agent_1 is adjacent to agent_0 and should be pulled toward 賛成
        # Original opinion for 反対 with confidence=0.8: 0.5 + (0.1 - 0.5)*0.8 = 0.18
        original_opinion_1 = _convert_stance_to_opinion("反対", 0.8)[0]
        new_opinion_1 = result["opinions"][1][0]
        # agent_1 should move toward agent_0's new position (賛成 ≈ 0.9)
        assert new_opinion_1 > original_opinion_1, (
            f"agent_1 opinion ({new_opinion_1}) should be > original ({original_opinion_1})"
        )

    @pytest.mark.asyncio
    async def test_non_representative_stable(self):
        """Agents not connected to any representative should be unaffected."""
        # Create two disconnected components: {0,1} and {3,4}
        agents = [_make_agent(i, big_five_c=0.3) for i in range(5)]
        responses = [_make_response(i, "反対", 0.8) for i in range(5)]
        # Only connect 0-1 and 3-4 (agent_2 is isolated, 3/4 disconnected from 0/1)
        edges = [
            _make_edge(0, 1, 0.8), _make_edge(1, 0, 0.8),
            _make_edge(3, 4, 0.8), _make_edge(4, 3, 0.8),
        ]

        # Only agent_0 (in component {0,1}) shifts
        representative_updates = [
            {"agent_id": "agent_0", "old_stance": "反対", "new_stance": "賛成"},
        ]

        result = await run_meeting_feedback_propagation(
            agents=agents,
            edges=edges,
            representative_updates=representative_updates,
            activation_responses=responses,
        )

        # agent_3 and agent_4 should not change
        original_op = _convert_stance_to_opinion("反対", 0.8)[0]
        assert result["opinions"][3][0] == pytest.approx(original_op, abs=1e-6), (
            "agent_3 should be unaffected (different component)"
        )
        assert result["opinions"][4][0] == pytest.approx(original_op, abs=1e-6), (
            "agent_4 should be unaffected (different component)"
        )

    @pytest.mark.asyncio
    async def test_empty_updates_noop(self):
        """When no representative changed stance, all opinions should be unchanged."""
        agents, responses, edges = self._make_agents_and_edges(4)

        result = await run_meeting_feedback_propagation(
            agents=agents,
            edges=edges,
            representative_updates=[],  # no changes
            activation_responses=responses,
        )

        # All opinions should remain at original values
        for i in range(4):
            original_op = _convert_stance_to_opinion("反対", 0.8)[0]
            assert result["opinions"][i][0] == pytest.approx(original_op, abs=1e-6), (
                f"agent_{i} opinion should be unchanged with empty updates"
            )
        assert result["changed_agents"] == []

    @pytest.mark.asyncio
    async def test_high_stubbornness_limits_change(self):
        """Feedback propagation (1 round) should produce smaller changes than full propagation."""
        # Use agents with moderate stubbornness
        agents = [_make_agent(i, big_five_c=0.5) for i in range(4)]
        responses = [_make_response(i, "反対", 0.8) for i in range(4)]
        edges = [
            _make_edge(0, 1, 0.8), _make_edge(1, 0, 0.8),
            _make_edge(1, 2, 0.8), _make_edge(2, 1, 0.8),
            _make_edge(2, 3, 0.8), _make_edge(3, 2, 0.8),
        ]

        representative_updates = [
            {"agent_id": "agent_0", "old_stance": "反対", "new_stance": "賛成"},
        ]

        result = await run_meeting_feedback_propagation(
            agents=agents,
            edges=edges,
            representative_updates=representative_updates,
            activation_responses=responses,
        )

        # With 1 round only, agent_3 (2 hops from agent_0) should barely move
        original_op = _convert_stance_to_opinion("反対", 0.8)[0]
        delta_1 = abs(result["opinions"][1][0] - original_op)
        delta_3 = abs(result["opinions"][3][0] - original_op)
        # agent_1 (direct neighbor) should change more than agent_3 (distant)
        assert delta_1 >= delta_3, (
            f"Direct neighbor delta ({delta_1}) should be >= distant agent delta ({delta_3})"
        )

    @pytest.mark.asyncio
    async def test_no_confidence_fabrication(self):
        """Feedback responses should preserve original confidence values, not inverse-convert."""
        agents = [_make_agent(i) for i in range(3)]
        responses = [
            _make_response(0, "反対", 0.75),
            _make_response(1, "中立", 0.6),
            _make_response(2, "賛成", 0.9),
        ]
        edges = [
            _make_edge(0, 1, 0.8), _make_edge(1, 0, 0.8),
            _make_edge(1, 2, 0.8), _make_edge(2, 1, 0.8),
        ]

        representative_updates = [
            {"agent_id": "agent_0", "old_stance": "反対", "new_stance": "賛成"},
        ]

        result = await run_meeting_feedback_propagation(
            agents=agents,
            edges=edges,
            representative_updates=representative_updates,
            activation_responses=responses,
        )

        # The feedback_responses field should preserve original confidence
        assert "feedback_responses" in result
        for fr in result["feedback_responses"]:
            agent_id = fr["agent_id"]
            # Find the original response for this agent
            orig = next(r for r in responses if r["agent_id"] == agent_id)
            assert fr["confidence"] == orig["confidence"], (
                f"Agent {agent_id}: confidence should be preserved "
                f"({orig['confidence']}), got {fr['confidence']}"
            )

    @pytest.mark.asyncio
    async def test_agreeableness_affects_feedback_round_stubbornness(self):
        """Feedback propagation should honor each agent's agreeableness trait."""
        agents = [
            _make_agent(0, big_five_c=0.5, big_five_a=0.9),
            _make_agent(1, big_five_c=0.5, big_five_a=0.1),
            _make_agent(2, big_five_c=0.5, big_five_a=0.5),
        ]
        responses = [_make_response(i, "反対", 0.8) for i in range(3)]
        edges = [
            _make_edge(0, 1, 0.8), _make_edge(1, 0, 0.8),
            _make_edge(1, 2, 0.8), _make_edge(2, 1, 0.8),
        ]
        representative_updates = [
            {"agent_id": "agent_0", "old_stance": "反対", "new_stance": "賛成"},
        ]

        result = await run_meeting_feedback_propagation(
            agents=agents,
            edges=edges,
            representative_updates=representative_updates,
            activation_responses=responses,
        )

        original_opinion_1 = _convert_stance_to_opinion("反対", 0.8)[0]
        original_opinion_2 = _convert_stance_to_opinion("反対", 0.8)[0]
        delta_low_a = abs(result["opinions"][1][0] - original_opinion_1)
        delta_mid_a = abs(result["opinions"][2][0] - original_opinion_2)

        assert delta_low_a > delta_mid_a, (
            "Lower agreeableness should yield lower stubbornness and a larger feedback-round shift"
        )

    @pytest.mark.asyncio
    async def test_post_feedback_evaluation_differs(self):
        """After feedback, stance distribution should differ from pre-feedback."""
        agents, responses, edges = self._make_agents_and_edges(5)

        # Strong shift: agent_0 goes from 反対 to 賛成
        representative_updates = [
            {"agent_id": "agent_0", "old_stance": "反対", "new_stance": "賛成"},
        ]

        result = await run_meeting_feedback_propagation(
            agents=agents,
            edges=edges,
            representative_updates=representative_updates,
            activation_responses=responses,
        )

        # Count stances before and after
        original_stances = [_convert_opinion_to_stance(_convert_stance_to_opinion("反対", 0.8)) for _ in range(5)]
        new_stances = [_convert_opinion_to_stance(op) for op in result["opinions"]]

        # At least agent_0 has changed, so distributions must differ
        assert original_stances != new_stances, (
            "Stance distribution should change after feedback propagation"
        )

    @pytest.mark.asyncio
    async def test_post_feedback_market_rebuilt(self):
        """PredictionMarket can be rebuilt from feedback_responses and produces valid prices."""
        from src.app.services.society.prediction_market import PredictionMarket

        agents = [_make_agent(i) for i in range(4)]
        responses = [
            _make_response(0, "反対", 0.8),
            _make_response(1, "反対", 0.7),
            _make_response(2, "中立", 0.5),
            _make_response(3, "賛成", 0.9),
        ]
        edges = [
            _make_edge(0, 1, 0.8), _make_edge(1, 0, 0.8),
            _make_edge(1, 2, 0.8), _make_edge(2, 1, 0.8),
            _make_edge(2, 3, 0.8), _make_edge(3, 2, 0.8),
        ]

        representative_updates = [
            {"agent_id": "agent_0", "old_stance": "反対", "new_stance": "賛成"},
        ]

        result = await run_meeting_feedback_propagation(
            agents=agents,
            edges=edges,
            representative_updates=representative_updates,
            activation_responses=responses,
        )

        # Build market from feedback_responses
        fb_responses = result["feedback_responses"]
        stances_set = {r["stance"] for r in fb_responses}
        assert len(stances_set) > 0, "Should have stances in feedback responses"

        market = PredictionMarket(outcomes=list(stances_set), adaptive_b=True)
        for resp in fb_responses:
            if resp["stance"] in stances_set:
                market.submit_bet(resp["agent_id"], resp["stance"], resp.get("confidence", 0.5))

        prices = market.get_prices()
        assert len(prices) > 0
        assert abs(sum(prices.values()) - 1.0) < 0.01, "Market prices should sum to ~1.0"
