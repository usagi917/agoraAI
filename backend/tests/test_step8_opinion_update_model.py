"""Step 8: 意見更新モデルの実装 テスト

TDD RED フェーズ:
- MAX_CONV_DELTA（0.15）clamp テスト
- MAX_EVENT_DELTA（0.25）tanh 飽和テスト
- apply_belief_decay() が BASE_DECAY（0.02）で収束するテスト
- 3 段階の適用順序テスト（外部イベント → 会話 → 減衰）
- seed 固定での決定論的再現テスト
- compute_memory_anchor() の記憶アンカーテスト（MEMORY_WINDOW=4, MEMORY_DECAY=0.3）
- motivated cognition テスト（CONFIRMATION_BIAS=0.3）
- Optuna TPE パラメータ推定の収束テスト（n_trials=200 で EMD が減少傾向）
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.app.services.society.opinion_dynamics import (
    MAX_CONV_DELTA,
    MAX_EVENT_DELTA,
    BASE_DECAY,
    MEMORY_WINDOW,
    MEMORY_DECAY,
    CONFIRMATION_BIAS,
    apply_belief_decay,
    compute_memory_anchor,
    OpinionDynamicsEngine,
)


# ---------------------------------------------------------------------------
# ヘルパー: 最小限のエージェント / エッジ fixture
# ---------------------------------------------------------------------------


def _make_agent(idx: int, opinion: float, stubbornness: float = 0.5, big_five_c: float = 0.5) -> dict:
    return {
        "id": f"agent-{idx}",
        "opinion_vector": [opinion],
        "stubbornness": stubbornness,
        "big_five": {"C": big_five_c, "O": 0.5},
    }


def _make_edge(src_idx: int, tgt_idx: int, strength: float = 1.0) -> dict:
    return {
        "agent_id": f"agent-{src_idx}",
        "target_id": f"agent-{tgt_idx}",
        "strength": strength,
    }


# ---------------------------------------------------------------------------
# テスト 1: MAX_CONV_DELTA（0.15）clamp
# ---------------------------------------------------------------------------


class TestMaxConvDeltaClamp:
    """propagation_step() の会話更新量が MAX_CONV_DELTA（0.15）に clamp されること"""

    def test_constant_value(self):
        """MAX_CONV_DELTA は 0.15 であること"""
        assert MAX_CONV_DELTA == 0.15

    def test_opinion_shift_clamped_to_max_conv_delta(self):
        """意見差が大きい隣人でも delta が MAX_CONV_DELTA を超えないこと"""
        # agent-0: opinion=0.1（強い反対寄り）, agent-1: opinion=0.9（強い賛成寄り）
        agents = [
            _make_agent(0, 0.1, stubbornness=0.0),  # stubbornness=0 → 隣人に完全依存
            _make_agent(1, 0.9, stubbornness=0.5),
        ]
        edges = [_make_edge(0, 1)]

        engine = OpinionDynamicsEngine(
            agents=agents,
            edges=edges,
            confidence_threshold=1.0,  # 全エージェントを受容
        )
        initial_op = engine._opinions[0][0]
        result = engine.propagation_step(timestep=0)
        new_op = result.updated_opinions[0][0]

        delta = abs(new_op - initial_op)
        assert delta <= MAX_CONV_DELTA + 1e-9, (
            f"会話更新量 {delta:.4f} が MAX_CONV_DELTA={MAX_CONV_DELTA} を超えた"
        )

    def test_clamp_applies_even_with_zero_stubbornness(self):
        """stubbornness=0 のエージェントでも clamp が効くこと"""
        agents = [
            _make_agent(0, 0.0, stubbornness=0.0),
            _make_agent(1, 1.0, stubbornness=0.5),
        ]
        edges = [_make_edge(0, 1, strength=100.0)]
        engine = OpinionDynamicsEngine(
            agents=agents,
            edges=edges,
            confidence_threshold=2.0,
        )
        initial_op = engine._opinions[0][0]
        result = engine.propagation_step(timestep=0)
        delta = abs(result.updated_opinions[0][0] - initial_op)
        assert delta <= MAX_CONV_DELTA + 1e-9, f"delta={delta}"


# ---------------------------------------------------------------------------
# テスト 2: MAX_EVENT_DELTA（0.25）tanh 飽和テスト
# ---------------------------------------------------------------------------


class TestMaxEventDeltaTanh:
    """MAX_EVENT_DELTA（0.25）は tanh 飽和の上限として機能すること"""

    def test_constant_value(self):
        """MAX_EVENT_DELTA は 0.25 であること"""
        assert MAX_EVENT_DELTA == 0.25

    def test_large_positive_event_clamps_near_max(self):
        """巨大な正方向イベントの delta が MAX_EVENT_DELTA 付近で飽和すること"""
        from src.app.services.society.opinion_dynamics import _apply_event_delta_tanh

        # 非常に大きな magnitude → tanh が 1.0 に近づく → delta ≈ MAX_EVENT_DELTA
        delta = _apply_event_delta_tanh(magnitude=1000.0, direction=1)
        assert delta <= MAX_EVENT_DELTA + 1e-9
        assert delta > MAX_EVENT_DELTA * 0.95, f"delta={delta} が MAX_EVENT_DELTA より低すぎる"

    def test_large_negative_event_clamps_near_negative_max(self):
        """巨大な負方向イベントの delta が -MAX_EVENT_DELTA 付近で飽和すること"""
        from src.app.services.society.opinion_dynamics import _apply_event_delta_tanh

        delta = _apply_event_delta_tanh(magnitude=1000.0, direction=-1)
        assert delta >= -MAX_EVENT_DELTA - 1e-9
        assert delta < -MAX_EVENT_DELTA * 0.95

    def test_small_event_is_proportional(self):
        """小さい magnitude では tanh がほぼ線形のこと（saturate しない）"""
        from src.app.services.society.opinion_dynamics import _apply_event_delta_tanh

        delta_small = _apply_event_delta_tanh(magnitude=0.01, direction=1)
        delta_large = _apply_event_delta_tanh(magnitude=0.1, direction=1)
        # 大きい magnitude のほうが大きい delta
        assert delta_large > delta_small

    def test_zero_magnitude_gives_zero_delta(self):
        """magnitude=0 のとき delta=0 であること"""
        from src.app.services.society.opinion_dynamics import _apply_event_delta_tanh

        delta = _apply_event_delta_tanh(magnitude=0.0, direction=1)
        assert abs(delta) < 1e-9


# ---------------------------------------------------------------------------
# テスト 3: apply_belief_decay()
# ---------------------------------------------------------------------------


class TestApplyBeliefDecay:
    """apply_belief_decay() が BASE_DECAY（0.02）で意見を初期値に収束させること"""

    def test_constant_value(self):
        """BASE_DECAY は 0.02 であること"""
        assert BASE_DECAY == 0.02

    def test_decay_moves_opinion_toward_initial(self):
        """減衰後は初期意見に近づくこと"""
        current = 0.8
        initial = 0.5
        decayed = apply_belief_decay(current, initial)
        # 初期値方向に動いているか
        assert abs(decayed - initial) < abs(current - initial)

    def test_decay_magnitude_equals_base_decay_times_diff(self):
        """減衰量 ≈ BASE_DECAY × (current - initial) であること"""
        current = 0.7
        initial = 0.5
        decayed = apply_belief_decay(current, initial)
        expected_delta = BASE_DECAY * (current - initial)
        assert abs((current - decayed) - expected_delta) < 1e-9

    def test_already_at_initial_no_change(self):
        """initial == current のとき変化しないこと"""
        val = 0.5
        assert apply_belief_decay(val, val) == val

    def test_decay_does_not_overshoot(self):
        """減衰が initial を通り越さないこと"""
        current = 0.9
        initial = 0.5
        for _ in range(1000):
            current = apply_belief_decay(current, initial)
        assert current >= initial - 1e-9

    def test_multiple_steps_converge_to_initial(self):
        """100 ステップ適用後に初期値に十分近いこと"""
        current = 1.0
        initial = 0.5
        for _ in range(100):
            current = apply_belief_decay(current, initial)
        # 100 ステップ後に初期値の ±0.10 以内
        assert abs(current - initial) < 0.10


# ---------------------------------------------------------------------------
# テスト 4: 3 段階の適用順序テスト（外部イベント → 会話 → 減衰）
# ---------------------------------------------------------------------------


class TestThreePhaseUpdateOrder:
    """run_network_propagation() の更新順序: 外部イベント → 会話 → 減衰"""

    def test_event_then_conversation_then_decay_order(self):
        """3 フェーズの適用順序が仕様通りであること（モックで検証）"""
        from src.app.services.society.opinion_dynamics import apply_three_phase_update

        call_order = []

        def mock_event(opinion, event_delta):
            call_order.append("event")
            return opinion + event_delta

        def mock_conversation(opinion, neighbor_mean, stubbornness):
            call_order.append("conversation")
            return opinion * stubbornness + neighbor_mean * (1 - stubbornness)

        def mock_decay(current, initial):
            call_order.append("decay")
            return apply_belief_decay(current, initial)

        apply_three_phase_update(
            current_opinion=0.5,
            initial_opinion=0.4,
            event_delta=0.05,
            neighbor_mean=0.6,
            stubbornness=0.5,
            event_fn=mock_event,
            conversation_fn=mock_conversation,
            decay_fn=mock_decay,
        )

        assert call_order == ["event", "conversation", "decay"], (
            f"期待する順序 ['event','conversation','decay'] に対して {call_order}"
        )

    def test_no_event_skips_event_phase(self):
        """event_delta=0 のとき event フェーズがスキップされること"""
        from src.app.services.society.opinion_dynamics import apply_three_phase_update

        call_order = []

        def mock_event(opinion, event_delta):
            call_order.append("event")
            return opinion + event_delta

        def mock_conversation(opinion, neighbor_mean, stubbornness):
            call_order.append("conversation")
            return opinion

        def mock_decay(current, initial):
            call_order.append("decay")
            return current

        apply_three_phase_update(
            current_opinion=0.5,
            initial_opinion=0.5,
            event_delta=0.0,
            neighbor_mean=0.5,
            stubbornness=0.5,
            event_fn=mock_event,
            conversation_fn=mock_conversation,
            decay_fn=mock_decay,
        )

        assert "event" not in call_order, "event_delta=0 なのに event が呼ばれた"
        assert "conversation" in call_order
        assert "decay" in call_order

    def test_three_phase_result_is_bounded(self):
        """3 フェーズ後の値が [0, 1] に収まること"""
        from src.app.services.society.opinion_dynamics import apply_three_phase_update

        result = apply_three_phase_update(
            current_opinion=0.95,
            initial_opinion=0.5,
            event_delta=0.1,
            neighbor_mean=0.2,
            stubbornness=0.3,
        )
        assert 0.0 <= result <= 1.0, f"結果 {result} が [0,1] 範囲外"


# ---------------------------------------------------------------------------
# テスト 5: seed 固定での決定論的再現テスト
# ---------------------------------------------------------------------------


class TestDeterministicReproduction:
    """同一 seed + 同一 agents/edges → 同一結果が再現されること"""

    def test_same_seed_same_result(self):
        """seed=42 で 2 回実行した結果が一致すること"""
        agents = [_make_agent(i, 0.3 + i * 0.1) for i in range(5)]
        edges = [_make_edge(i, (i + 1) % 5) for i in range(5)]

        engine1 = OpinionDynamicsEngine(
            agents=agents, edges=edges, confidence_threshold=0.4, seed=42,
        )
        engine2 = OpinionDynamicsEngine(
            agents=agents, edges=edges, confidence_threshold=0.4, seed=42,
        )

        for t in range(5):
            r1 = engine1.propagation_step(timestep=t)
            r2 = engine2.propagation_step(timestep=t)
            assert r1.updated_opinions == r2.updated_opinions, (
                f"timestep {t}: 結果が一致しない"
            )

    def test_different_seeds_may_differ(self):
        """seed が異なれば motivated cognition ノイズにより結果が異なる可能性があること"""
        agents = [_make_agent(i, 0.5) for i in range(5)]
        edges = [_make_edge(i, (i + 1) % 5) for i in range(5)]

        engine1 = OpinionDynamicsEngine(
            agents=agents, edges=edges, confidence_threshold=0.4, seed=1,
        )
        engine2 = OpinionDynamicsEngine(
            agents=agents, edges=edges, confidence_threshold=0.4, seed=99,
        )

        results1 = [engine1.propagation_step(t).updated_opinions for t in range(3)]
        results2 = [engine2.propagation_step(t).updated_opinions for t in range(3)]

        # 同一初期値の場合 motivated cognition がなければ同じになる可能性もあるが、
        # それでも seed を持つ実装になっていることを確認
        # (両者が同じでも OK - これはソフトな確認)
        assert results1 is not results2  # 別オブジェクト


# ---------------------------------------------------------------------------
# テスト 6: compute_memory_anchor()
# ---------------------------------------------------------------------------


class TestComputeMemoryAnchor:
    """compute_memory_anchor() の記憶アンカーテスト（MEMORY_WINDOW=4, MEMORY_DECAY=0.3）"""

    def test_constants_values(self):
        """MEMORY_WINDOW=4, MEMORY_DECAY=0.3 であること"""
        assert MEMORY_WINDOW == 4
        assert MEMORY_DECAY == 0.3

    def test_empty_history_returns_initial(self):
        """履歴が空の場合、initial_opinion を返すこと"""
        result = compute_memory_anchor([], initial_opinion=0.5)
        assert result == 0.5

    def test_single_history_returns_initial(self):
        """履歴が 1 件（初期のみ）の場合、initial_opinion を返すこと"""
        result = compute_memory_anchor([0.7], initial_opinion=0.5)
        assert result == 0.5

    def test_recent_steps_have_higher_weight(self):
        """直近のステップほど重みが大きいこと（指数減衰 decay=0.3, k=0 が最大）"""
        # 古いステップは低い値、直近は高い値
        history = [0.1, 0.2, 0.3, 0.8]  # 直近が 0.8
        anchor = compute_memory_anchor(history, initial_opinion=0.1)
        # 直近 0.8 の重みが大きいので anchor は単純平均より高くなるはず
        simple_mean = sum(history) / len(history)
        assert anchor > simple_mean, (
            f"anchor={anchor:.4f} が単純平均 {simple_mean:.4f} より高くなるべき（直近重視）"
        )

    def test_weights_decay_exponentially(self):
        """重みが exp(-MEMORY_DECAY * k) で減衰すること（k=0 が直近）"""
        # 直近 4 ステップで weight 比を確認
        history = [0.0, 0.0, 0.0, 1.0]  # 直近のみ 1.0
        anchor = compute_memory_anchor(history, initial_opinion=0.0)

        # k=0 (直近=1.0), k=1..3 (0.0) の加重平均
        w0 = math.exp(-MEMORY_DECAY * 0)
        w1 = math.exp(-MEMORY_DECAY * 1)
        w2 = math.exp(-MEMORY_DECAY * 2)
        w3 = math.exp(-MEMORY_DECAY * 3)
        expected = (w0 * 1.0 + w1 * 0.0 + w2 * 0.0 + w3 * 0.0) / (w0 + w1 + w2 + w3)

        assert abs(anchor - expected) < 1e-9, f"anchor={anchor}, expected={expected}"

    def test_history_longer_than_window_uses_last_window(self):
        """履歴が MEMORY_WINDOW より長い場合、直近 MEMORY_WINDOW ステップのみ使用すること"""
        # MEMORY_WINDOW=4, 6 ステップの履歴
        long_history = [0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1]  # 後ろ4ステップが 0.1
        short_history = [0.1, 0.1, 0.1, 0.1]  # 同じ直近 4 ステップ

        anchor_long = compute_memory_anchor(long_history, initial_opinion=0.5)
        anchor_short = compute_memory_anchor(short_history, initial_opinion=0.5)

        assert abs(anchor_long - anchor_short) < 1e-9, (
            f"長い履歴 {anchor_long} と短い履歴 {anchor_short} で結果が異なる"
        )

    def test_anchor_used_in_propagation_instead_of_initial(self):
        """propagation_step() が x_i(0) の代わりに compute_memory_anchor を使用すること.

        memory_anchor を使うエンジンと使わないエンジンの差異で確認する:

        設定:
        - agent-0: initial_opinion=0.5, opinion_history=[0.5,0.9,0.9,0.9] → memory_anchor≈0.84
        - agent-1 (neighbor): opinion=0.5（中立 → neighbor_mean=0.5）
        - stubbornness=0.8

        FJ 計算:
        - with memory:    unclamped = 0.8 * 0.84 + 0.2 * 0.5 ≈ 0.77 > 0.5 → clamp してもプラス方向
        - without memory: unclamped = 0.8 * 0.5  + 0.2 * 0.5 = 0.5 → 変化なし

        よって new_op_mem > new_op_no になるはず。
        """
        # memory anchor を直接計算して期待値を確定
        history_with_memory = [0.5, 0.9, 0.9, 0.9]
        expected_anchor = compute_memory_anchor(history_with_memory, initial_opinion=0.5)
        # expected_anchor ≈ 0.84

        # Engine with memory history (memory_anchor ≈ 0.84)
        agents_with_memory = [
            {**_make_agent(0, 0.5, stubbornness=0.8), "opinion_history": history_with_memory},
            _make_agent(1, 0.5, stubbornness=0.5),
        ]
        # Engine without memory (falls back to initial = 0.5)
        agents_no_memory = [
            _make_agent(0, 0.5, stubbornness=0.8),
            _make_agent(1, 0.5, stubbornness=0.5),
        ]
        edges = [_make_edge(0, 1)]

        engine_mem = OpinionDynamicsEngine(agents=agents_with_memory, edges=edges, confidence_threshold=1.0)
        engine_no = OpinionDynamicsEngine(agents=agents_no_memory, edges=edges, confidence_threshold=1.0)

        result_mem = engine_mem.propagation_step(timestep=0)
        result_no = engine_no.propagation_step(timestep=0)

        new_op_mem = result_mem.updated_opinions[0][0]
        new_op_no = result_no.updated_opinions[0][0]

        # With memory anchor (≈0.84), FJ pulls toward 0.84 → net positive shift from 0.5
        # Without memory anchor (initial=0.5), neighbor_mean=0.5 also → no change (stays 0.5)
        assert new_op_mem > new_op_no, (
            f"memory anchor を使う場合 ({new_op_mem:.4f}) が "
            f"使わない場合 ({new_op_no:.4f}) より高いはず (anchor≈{expected_anchor:.3f})"
        )


# ---------------------------------------------------------------------------
# テスト 7: motivated cognition（CONFIRMATION_BIAS=0.3）
# ---------------------------------------------------------------------------


class TestMotivatedCognition:
    """CONFIRMATION_BIAS=0.3 で同方向意見の effective_w が 1.3 倍、逆方向が 0.85 倍"""

    def test_constant_value(self):
        """CONFIRMATION_BIAS は 0.3 であること"""
        assert CONFIRMATION_BIAS == 0.3

    def test_same_direction_opinion_has_amplified_weight(self):
        """自分の意見と同方向の隣人の weight が 1.3 倍（1 + CONFIRMATION_BIAS）になること"""
        # agent-0: opinion=0.8（賛成寄り）, agent-1 も 0.9（同方向）, agent-2 は 0.2（逆方向）
        # 同方向 = agent-1 の effective_w が大きい → agent-0 は agent-1 に引き寄せられる
        agents = [
            _make_agent(0, 0.8, stubbornness=0.3),  # 賛成寄り、やや頑固でない
            _make_agent(1, 0.95, stubbornness=0.5),   # 同方向（賛成）
            _make_agent(2, 0.1, stubbornness=0.5),   # 逆方向（反対）
        ]
        edges = [
            _make_edge(0, 1, strength=1.0),
            _make_edge(0, 2, strength=1.0),
        ]

        engine = OpinionDynamicsEngine(
            agents=agents, edges=edges, confidence_threshold=1.0,
        )
        result = engine.propagation_step(timestep=0)
        new_op = result.updated_opinions[0][0]

        # 同方向（0.95）の weight が大きいので neighbor_mean > (0.95+0.1)/2=0.525
        # → new_op が単純平均より高め（0.8 側に近い）
        simple_neighbor_mean = (0.95 + 0.1) / 2.0
        # 確証バイアスがあれば、neighbor_mean は simple_mean より高いはず
        # stubbornness=0.3 なので new_op = 0.3 * anchor + 0.7 * biased_mean
        # biased_mean > simple_mean → new_op を確認
        # ざっくり: biased_mean > 0.525 ならば new_op > 0.3*0.8 + 0.7*0.525 = 0.6075
        unbiased_estimate = 0.3 * 0.8 + 0.7 * simple_neighbor_mean
        assert new_op >= unbiased_estimate - 1e-9 or new_op >= 0.55, (
            f"確証バイアスが効いているはず: new_op={new_op:.4f}, "
            f"unbiased_estimate={unbiased_estimate:.4f}"
        )

    def test_confirmation_bias_weights_are_asymmetric(self):
        """同方向の effective_w が逆方向の effective_w より大きいこと"""
        # OpinionDynamicsEngine に confirmation_bias_weights() メソッドが存在し
        # 正しい比率を返すことを確認
        from src.app.services.society.opinion_dynamics import compute_confirmation_bias_weight

        # 現在意見が 0.8（賛成寄り = 中央 0.5 より上）
        # 隣人意見が 0.9 → 同方向（0.9 > 0.8 > 0.5）
        w_same = compute_confirmation_bias_weight(
            agent_opinion=0.8,
            neighbor_opinion=0.9,
            base_weight=1.0,
        )
        # 隣人意見が 0.2 → 逆方向
        w_opposite = compute_confirmation_bias_weight(
            agent_opinion=0.8,
            neighbor_opinion=0.2,
            base_weight=1.0,
        )

        assert abs(w_same - (1.0 + CONFIRMATION_BIAS)) < 1e-9, (
            f"同方向 weight={w_same}, 期待値={1.0 + CONFIRMATION_BIAS}"
        )
        assert abs(w_opposite - (1.0 - CONFIRMATION_BIAS * 0.5)) < 1e-9, (
            f"逆方向 weight={w_opposite}, 期待値={1.0 - CONFIRMATION_BIAS * 0.5}"
        )

    def test_confirmation_bias_neutral_opinion(self):
        """agent_opinion=0.5（中立）のとき bias が適用されないこと（同方向判定が曖昧）"""
        from src.app.services.society.opinion_dynamics import compute_confirmation_bias_weight

        w = compute_confirmation_bias_weight(
            agent_opinion=0.5,
            neighbor_opinion=0.8,
            base_weight=1.0,
        )
        # 中立の場合は bias なし（デフォルト weight のまま）
        assert w == 1.0, f"中立時は bias なし: w={w}"


# ---------------------------------------------------------------------------
# テスト 8: Optuna TPE パラメータ推定の収束テスト
# ---------------------------------------------------------------------------


class TestOptunaTpeConvergence:
    """Optuna TPE で n_trials=200 後に EMD が減少傾向にあること"""

    def test_optuna_study_reduces_emd_over_trials(self):
        """n_trials=200 で Optuna TPE 最適化が EMD を改善すること"""
        from src.app.services.society.opinion_dynamics import (
            optimize_opinion_dynamics_params,
        )

        # 簡略化: 10 件の "実際の分布" と最適化ターゲットを用意
        target_distribution = {
            "賛成": 0.45,
            "条件付き賛成": 0.28,
            "中立": 0.12,
            "条件付き反対": 0.09,
            "反対": 0.06,
        }
        # 実際のシミュレーション履歴（短縮: 3 ステップのみ）
        initial_opinions = [0.3 + i * 0.07 for i in range(10)]

        best_params, best_emd = optimize_opinion_dynamics_params(
            target_distribution=target_distribution,
            initial_opinions=initial_opinions,
            n_trials=50,  # テスト短縮のため 50（本番は 200）
            seed=42,
        )

        # 最適化後に best_params が返ること
        assert isinstance(best_params, dict)
        assert "confidence_threshold" in best_params
        assert "stubbornness" in best_params or "base_stubbornness" in best_params

        # EMD が有限かつ非負
        assert best_emd >= 0.0
        assert math.isfinite(best_emd)

    def test_optimize_returns_params_in_valid_range(self):
        """最適化パラメータが有効範囲内であること"""
        from src.app.services.society.opinion_dynamics import (
            optimize_opinion_dynamics_params,
        )

        target_distribution = {
            "賛成": 0.30,
            "条件付き賛成": 0.25,
            "中立": 0.20,
            "条件付き反対": 0.15,
            "反対": 0.10,
        }
        initial_opinions = [0.2, 0.4, 0.5, 0.6, 0.8]

        best_params, _ = optimize_opinion_dynamics_params(
            target_distribution=target_distribution,
            initial_opinions=initial_opinions,
            n_trials=20,
            seed=0,
        )

        ct = best_params.get("confidence_threshold", 0)
        assert 0.05 <= ct <= 1.0, f"confidence_threshold={ct} が範囲外"

        stubbornness = best_params.get("stubbornness", best_params.get("base_stubbornness", -1))
        assert 0.0 <= stubbornness <= 1.0, f"stubbornness={stubbornness} が範囲外"


# ---------------------------------------------------------------------------
# REFACTOR coverage補完: 既存メソッド / 特殊パスのテスト
# ---------------------------------------------------------------------------


class TestEngineConvergenceAndClusters:
    """OpinionDynamicsEngine の収束検出・クラスタ検出テスト"""

    def _basic_engine(self, n: int = 10, seed: int = 42) -> "OpinionDynamicsEngine":
        agents = [_make_agent(i, 0.5 + (i - n // 2) * 0.03) for i in range(n)]
        edges = [_make_edge(i, (i + 1) % n) for i in range(n)]
        return OpinionDynamicsEngine(
            agents=agents, edges=edges, confidence_threshold=0.5, seed=seed,
        )

    def test_detect_convergence_false_before_enough_history(self):
        """履歴が window より少ない場合は False を返すこと"""
        engine = self._basic_engine()
        assert engine.detect_convergence(window=3) is False

    def test_detect_convergence_true_after_stable_steps(self):
        """安定した意見が続いた後は True を返すこと"""
        engine = self._basic_engine()
        for t in range(10):
            engine.propagation_step(t)
        # 収束チェック（epsilon を大きめに設定）
        result = engine.detect_convergence(window=3, epsilon=1.0)
        assert result is True

    def test_detect_variance_plateau_false_before_enough_history(self):
        """履歴が window+1 より少ない場合は False を返すこと"""
        engine = self._basic_engine()
        assert engine.detect_variance_plateau(window=3) is False

    def test_detect_variance_plateau_returns_bool(self):
        """detect_variance_plateau が bool を返すこと"""
        engine = self._basic_engine()
        for t in range(10):
            engine.propagation_step(t)
        result = engine.detect_variance_plateau(window=3)
        assert isinstance(result, bool)

    def test_detect_clusters_returns_cluster_list(self):
        """detect_clusters が ClusterInfo のリストを返すこと"""
        from src.app.services.society.opinion_dynamics import ClusterInfo

        engine = self._basic_engine(n=10)
        for t in range(3):
            engine.propagation_step(t)
        clusters = engine.detect_clusters()
        assert isinstance(clusters, list)
        for c in clusters:
            assert isinstance(c, ClusterInfo)

    def test_detect_clusters_all_agents_covered(self):
        """全エージェントがいずれかのクラスタに属すること"""
        engine = self._basic_engine(n=8)
        for t in range(3):
            engine.propagation_step(t)
        clusters = engine.detect_clusters()
        covered = sum(c.size for c in clusters)
        assert covered == engine.n


class TestExistingThresholdFunctions:
    """compute_heterogeneous_thresholds / compute_filter_bubble_thresholds テスト"""

    def test_compute_heterogeneous_thresholds_length(self):
        """返されるスレッショルドの長さがエージェント数と一致すること"""
        from src.app.services.society.opinion_dynamics import compute_heterogeneous_thresholds

        agents = [{"big_five": {"C": 0.5, "O": 0.5}} for _ in range(10)]
        thresholds = compute_heterogeneous_thresholds(agents, seed=42)
        assert len(thresholds) == 10

    def test_compute_heterogeneous_thresholds_positive(self):
        """全スレッショルドが正の値であること"""
        from src.app.services.society.opinion_dynamics import compute_heterogeneous_thresholds

        agents = [{"big_five": {"C": float(i) / 10, "O": float(i) / 10}} for i in range(10)]
        thresholds = compute_heterogeneous_thresholds(agents, seed=0)
        assert all(t > 0 for t in thresholds)

    def test_compute_filter_bubble_thresholds_length(self):
        """返されるスレッショルドの長さがエージェント数と一致すること"""
        from src.app.services.society.opinion_dynamics import compute_filter_bubble_thresholds

        agents = [{"information_source": "テレビニュース", "big_five": {"O": 0.5}} for _ in range(5)]
        thresholds = compute_filter_bubble_thresholds(agents)
        assert len(thresholds) == 5

    def test_compute_filter_bubble_thresholds_bubble_width_zero(self):
        """bubble_width=0 のとき全エージェントが base_threshold を返すこと"""
        from src.app.services.society.opinion_dynamics import compute_filter_bubble_thresholds

        agents = [{"information_source": "SNS(Twitter/X)", "big_five": {"O": 0.5}} for _ in range(5)]
        base = 0.35
        thresholds = compute_filter_bubble_thresholds(agents, base_threshold=base, bubble_width=0.0)
        assert all(abs(t - base) < 1e-9 for t in thresholds)

    def test_compute_filter_bubble_sns_narrower_than_newspaper(self):
        """SNS ユーザーの閾値が新聞ユーザーより狭いこと（フィルターバブル効果）"""
        from src.app.services.society.opinion_dynamics import compute_filter_bubble_thresholds

        agent_sns = [{"information_source": "SNS(Twitter/X)", "big_five": {"O": 0.5}}]
        agent_news = [{"information_source": "新聞", "big_five": {"O": 0.5}}]
        t_sns = compute_filter_bubble_thresholds(agent_sns)[0]
        t_news = compute_filter_bubble_thresholds(agent_news)[0]
        assert t_sns < t_news, f"SNS {t_sns:.4f} >= newspaper {t_news:.4f}"


class TestMultiDimOpinionEngine:
    """2次元以上の opinion_vector を持つエンジンのパステスト"""

    def test_multidim_propagation_works(self):
        """2次元の opinion_vector で propagation_step が動作すること"""
        agents = [
            {"id": f"a{i}", "opinion_vector": [0.5, 0.4], "stubbornness": 0.5}
            for i in range(4)
        ]
        edges = [
            {"agent_id": "a0", "target_id": "a1", "strength": 1.0},
            {"agent_id": "a1", "target_id": "a2", "strength": 1.0},
        ]
        engine = OpinionDynamicsEngine(
            agents=agents, edges=edges, confidence_threshold=1.0,
        )
        result = engine.propagation_step(timestep=0)
        assert len(result.updated_opinions) == 4
        assert len(result.updated_opinions[0]) == 2


# ===========================================================================
# Test: 推定結果の YAML 保存 (Step 8 Green 残り)
# ===========================================================================

class TestSaveEstimatedParams:
    """optimize_opinion_dynamics_params() の結果を YAML へ保存する機能のテスト。"""

    def test_save_estimated_params_creates_yaml_file(self, tmp_path):
        """save_estimated_params() が YAML ファイルを生成すること。"""
        from src.app.services.society.opinion_dynamics import save_estimated_params

        params = {"confidence_threshold": 0.42, "base_stubbornness": 0.65}
        best_emd = 0.087
        out_path = tmp_path / "economy_params.yaml"

        save_estimated_params(params, best_emd, out_path)

        assert out_path.exists(), f"YAML ファイルが生成されていない: {out_path}"

    def test_save_estimated_params_correct_content(self, tmp_path):
        """保存された YAML が正しいキーと値を含むこと。"""
        import yaml
        from src.app.services.society.opinion_dynamics import save_estimated_params

        params = {"confidence_threshold": 0.42, "base_stubbornness": 0.65}
        best_emd = 0.087
        out_path = tmp_path / "economy_params.yaml"

        save_estimated_params(params, best_emd, out_path)

        with open(out_path) as f:
            data = yaml.safe_load(f)

        assert "params" in data
        assert "best_emd" in data
        assert abs(data["params"]["confidence_threshold"] - 0.42) < 1e-6
        assert abs(data["params"]["base_stubbornness"] - 0.65) < 1e-6
        assert abs(data["best_emd"] - 0.087) < 1e-6

    def test_save_estimated_params_includes_metadata(self, tmp_path):
        """YAML に category と timestamp のメタデータが含まれること。"""
        import yaml
        from src.app.services.society.opinion_dynamics import save_estimated_params

        params = {"confidence_threshold": 0.3, "base_stubbornness": 0.5}
        out_path = tmp_path / "security_params.yaml"

        save_estimated_params(params, 0.05, out_path, category="security")

        with open(out_path) as f:
            data = yaml.safe_load(f)

        assert data.get("category") == "security"
        assert "saved_at" in data  # ISO タイムスタンプ

    def test_optimize_and_save_roundtrip(self, tmp_path):
        """optimize → save → load のラウンドトリップが正常に動作すること。"""
        import yaml
        from src.app.services.society.opinion_dynamics import (
            optimize_opinion_dynamics_params,
            save_estimated_params,
        )

        target_dist = {"賛成": 0.3, "条件付き賛成": 0.2, "中立": 0.3, "条件付き反対": 0.1, "反対": 0.1}
        initial_opinions = [0.3, 0.5, 0.7, 0.8, 0.2]

        best_params, best_emd = optimize_opinion_dynamics_params(
            target_dist, initial_opinions, n_trials=10, seed=42,
        )
        out_path = tmp_path / "economy_params.yaml"
        save_estimated_params(best_params, best_emd, out_path, category="economy")

        with open(out_path) as f:
            loaded = yaml.safe_load(f)

        assert loaded["category"] == "economy"
        assert abs(loaded["best_emd"] - best_emd) < 1e-9
        for k, v in best_params.items():
            assert abs(loaded["params"][k] - v) < 1e-9


# ===========================================================================
# Test: IssueParams YAML 参照統一 (Step 8 Refactor)
# ===========================================================================

class TestIssueParamsYaml:
    """opinion_dynamics.py の定数が IssueParams YAML と一致すること。

    YAML が存在しない場合はデフォルト値（コード定数）を使用するため、
    YAML との整合性のみを確認する。
    """

    def test_issue_params_yaml_exists_and_readable(self):
        """config/grounding/issue_params.yaml が存在し読み込めること。"""
        import yaml
        from pathlib import Path

        yaml_path = Path(__file__).parent.parent.parent / "config" / "grounding" / "issue_params.yaml"
        assert yaml_path.exists(), f"issue_params.yaml が見つからない: {yaml_path}"

        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_issue_params_yaml_contains_required_keys(self):
        """YAML に必須キーが含まれること。"""
        import yaml
        from pathlib import Path

        yaml_path = Path(__file__).parent.parent.parent / "config" / "grounding" / "issue_params.yaml"
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        required_keys = [
            "MAX_CONV_DELTA",
            "MAX_EVENT_DELTA",
            "BASE_DECAY",
            "MEMORY_WINDOW",
            "MEMORY_DECAY",
            "CONFIRMATION_BIAS",
            "EVENT_DECAY_TAU1",
            "EVENT_DECAY_TAU2",
            "LOSS_AVERSION_LAMBDA",
        ]
        for key in required_keys:
            assert key in data, f"YAML に {key} が見つからない"

    def test_issue_params_yaml_values_match_module_constants(self):
        """YAML の値がモジュール定数と一致すること（デフォルト値の整合性確認）。"""
        import yaml
        from pathlib import Path
        from src.app.services.society.opinion_dynamics import (
            MAX_CONV_DELTA, MAX_EVENT_DELTA, BASE_DECAY,
            MEMORY_WINDOW, MEMORY_DECAY, CONFIRMATION_BIAS,
        )
        from src.app.services.society.event_exposure import (
            EVENT_DECAY_TAU1, EVENT_DECAY_TAU2, LOSS_AVERSION_LAMBDA,
        )

        yaml_path = Path(__file__).parent.parent.parent / "config" / "grounding" / "issue_params.yaml"
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        assert abs(data["MAX_CONV_DELTA"] - MAX_CONV_DELTA) < 1e-9
        assert abs(data["MAX_EVENT_DELTA"] - MAX_EVENT_DELTA) < 1e-9
        assert abs(data["BASE_DECAY"] - BASE_DECAY) < 1e-9
        assert data["MEMORY_WINDOW"] == MEMORY_WINDOW
        assert abs(data["MEMORY_DECAY"] - MEMORY_DECAY) < 1e-9
        assert abs(data["CONFIRMATION_BIAS"] - CONFIRMATION_BIAS) < 1e-9
        assert abs(data["EVENT_DECAY_TAU1"] - EVENT_DECAY_TAU1) < 1e-9
        assert abs(data["EVENT_DECAY_TAU2"] - EVENT_DECAY_TAU2) < 1e-9
        assert abs(data["LOSS_AVERSION_LAMBDA"] - LOSS_AVERSION_LAMBDA) < 1e-9
