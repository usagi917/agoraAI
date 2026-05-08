"""CascadePropagator のテスト: N ラウンド伝播 + bandwagon + 確信度減衰."""

from __future__ import annotations

import pytest

from src.app.services.communication.cascade_propagator import CascadePropagator


def _resp(agent_id: int, stance: str, confidence: float = 0.7) -> dict:
    return {"agent_id": agent_id, "stance": stance, "confidence": confidence}


# ---------------------------------------------------------------------------
# Basic propagation
# ---------------------------------------------------------------------------

def test_propagate_returns_per_round_snapshots():
    """propagate は各ラウンドのスナップショット (list[list[dict]]) を返す。"""
    propagator = CascadePropagator(num_rounds=3, decay_factor=0.9)
    initial = [
        _resp(0, "賛成", 0.8),
        _resp(1, "反対", 0.8),
        _resp(2, "中立", 0.5),
    ]
    edges = [(0, 1), (1, 2), (0, 2)]

    history = propagator.propagate(initial, edges)

    assert isinstance(history, list)
    # Round 0 (initial state) + 3 rounds = 4 snapshots
    assert len(history) == 4
    for snapshot in history:
        assert len(snapshot) == 3
        for r in snapshot:
            assert "agent_id" in r
            assert "stance" in r
            assert "confidence" in r
            assert 0.0 <= r["confidence"] <= 1.0


def test_propagate_runs_default_n5_rounds():
    """num_rounds=5 がデフォルトで適用される。"""
    propagator = CascadePropagator()
    initial = [_resp(i, "中立", 0.5) for i in range(4)]
    edges = [(0, 1), (1, 2), (2, 3)]

    history = propagator.propagate(initial, edges)

    assert len(history) == 6  # initial + 5 rounds


def test_propagate_rounds_override():
    """rounds 引数で num_rounds を上書きできる。"""
    propagator = CascadePropagator(num_rounds=5)
    initial = [_resp(i, "中立", 0.5) for i in range(3)]
    edges = [(0, 1), (1, 2)]

    history = propagator.propagate(initial, edges, rounds=2)

    assert len(history) == 3  # initial + 2 rounds


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_propagate_single_agent_no_edges():
    """単一エージェント・無辺ではスタンスは変化しない。"""
    propagator = CascadePropagator(num_rounds=3, decay_factor=0.9)
    initial = [_resp(0, "賛成", 0.8)]
    edges: list[tuple[int, int]] = []

    history = propagator.propagate(initial, edges)

    assert len(history) == 4
    for snapshot in history:
        assert snapshot[0]["stance"] == "賛成"


def test_propagate_no_edges_preserves_stances():
    """グラフ無辺なら全員のスタンスは初期値のまま。"""
    propagator = CascadePropagator(num_rounds=3)
    initial = [
        _resp(0, "賛成", 0.7),
        _resp(1, "反対", 0.7),
    ]
    edges: list[tuple[int, int]] = []

    history = propagator.propagate(initial, edges)

    final = history[-1]
    stance_by_id = {r["agent_id"]: r["stance"] for r in final}
    assert stance_by_id[0] == "賛成"
    assert stance_by_id[1] == "反対"


def test_confidence_decays_per_round():
    """各ラウンドで confidence が decay_factor で減衰する。"""
    propagator = CascadePropagator(num_rounds=3, decay_factor=0.5)
    initial = [_resp(0, "賛成", 1.0)]
    edges: list[tuple[int, int]] = []

    history = propagator.propagate(initial, edges)

    # round 0 = 1.0, round 1 = 0.5, round 2 = 0.25, round 3 = 0.125
    assert history[0][0]["confidence"] == pytest.approx(1.0)
    assert history[1][0]["confidence"] == pytest.approx(0.5)
    assert history[2][0]["confidence"] == pytest.approx(0.25)
    assert history[3][0]["confidence"] == pytest.approx(0.125)


# ---------------------------------------------------------------------------
# Bandwagon effect
# ---------------------------------------------------------------------------

def test_bandwagon_pulls_minority_toward_majority():
    """近傍多数派が "賛成" のとき少数派の中立エージェントは賛成に引かれる。"""
    propagator = CascadePropagator(num_rounds=5, decay_factor=0.95)
    # agent 0 = 中立、その近傍 1,2,3,4 が全員 "賛成"
    initial = [
        _resp(0, "中立", 0.5),
        _resp(1, "賛成", 0.9),
        _resp(2, "賛成", 0.9),
        _resp(3, "賛成", 0.9),
        _resp(4, "賛成", 0.9),
    ]
    edges = [(0, 1), (0, 2), (0, 3), (0, 4)]

    history = propagator.propagate(initial, edges)
    final = history[-1]
    stance_by_id = {r["agent_id"]: r["stance"] for r in final}

    # agent 0 should have been pulled toward 賛成 (or 条件付き賛成)
    assert stance_by_id[0] in {"賛成", "条件付き賛成"}


def test_propagation_changes_distribution_over_rounds():
    """5 ラウンドを通してスタンス分布が変化する (静止しない)。"""
    propagator = CascadePropagator(num_rounds=5, decay_factor=0.9)
    initial = [
        _resp(0, "賛成", 0.9),
        _resp(1, "賛成", 0.9),
        _resp(2, "賛成", 0.9),
        _resp(3, "反対", 0.6),
        _resp(4, "中立", 0.5),
    ]
    edges = [(3, 0), (3, 1), (3, 2), (4, 0), (4, 1)]

    history = propagator.propagate(initial, edges)

    initial_stances = tuple(r["stance"] for r in history[0])
    final_stances = tuple(r["stance"] for r in history[-1])
    assert initial_stances != final_stances


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------

def test_converged_returns_false_for_changing_history():
    """変化中の履歴では converged() は False。"""
    propagator = CascadePropagator()
    history = [
        [_resp(0, "賛成", 0.9), _resp(1, "反対", 0.9)],
        [_resp(0, "中立", 0.85), _resp(1, "中立", 0.85)],
    ]
    assert propagator.converged(history) is False


def test_converged_returns_true_for_stable_history():
    """連続する 2 ラウンドの分布変化が 1% 未満なら True。"""
    propagator = CascadePropagator()
    history = [
        [_resp(0, "賛成", 0.9), _resp(1, "反対", 0.9), _resp(2, "中立", 0.5)],
        [_resp(0, "賛成", 0.85), _resp(1, "反対", 0.85), _resp(2, "中立", 0.45)],
    ]
    assert propagator.converged(history) is True


def test_converged_handles_short_history():
    """履歴が 2 未満なら converged は False を返す。"""
    propagator = CascadePropagator()
    assert propagator.converged([]) is False
    assert propagator.converged([[_resp(0, "賛成")]]) is False
