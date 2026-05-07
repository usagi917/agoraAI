"""Step 9: 外部イベント注入 テスト

TDD RED フェーズ:
- compute_exposure() の属性別曝露確率テスト
- compute_trust() の情報源信頼度テスト
- compute_interpretation() の解釈方向テスト
- Prospect Theory 非対称テスト（negative direction で loss が LOSS_AVERSION_LAMBDA=2.25 倍）
- tanh 飽和テスト（raw magnitude >> MAX_EVENT_DELTA でも出力が MAX_EVENT_DELTA を超えない）
- Two-phase event decay テスト（TAU1=0.5, TAU2=4.0 で指数減衰が二段階）
- アブレーション 4 条件の差異テスト（イベントなし / 均一曝露 / 異質曝露 / 対称イベント）
"""

from __future__ import annotations

import math

import pytest

from src.app.services.society.event_exposure import (
    LOSS_AVERSION_LAMBDA,
    EVENT_DECAY_TAU1,
    EVENT_DECAY_TAU2,
    compute_exposure,
    compute_trust,
    compute_interpretation,
    compute_event_delta,
    event_residual,
    ablation_no_event,
    ablation_uniform_exposure,
    ablation_heterogeneous_exposure,
    ablation_symmetric_event,
)
from src.app.services.society.opinion_dynamics import MAX_EVENT_DELTA


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_agent(
    idx: int,
    opinion: float = 0.5,
    information_source: str = "テレビニュース",
    age: int = 40,
    region: str = "東京都",
    openness: float = 0.5,
) -> dict:
    return {
        "id": f"agent-{idx}",
        "opinion_vector": [opinion],
        "information_source": information_source,
        "demographics": {"age": age, "region": region, "occupation": "会社員"},
        "big_five": {"O": openness, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
    }


def _make_event(
    source: str = "テレビニュース",
    framing: str = "positive",
    magnitude: float = 0.3,
    medium: str = "broadcast",
) -> dict:
    return {
        "id": "event-1",
        "source": source,
        "framing": framing,
        "magnitude": magnitude,
        "medium": medium,
    }


# ---------------------------------------------------------------------------
# 定数テスト
# ---------------------------------------------------------------------------


class TestConstants:
    def test_loss_aversion_lambda(self):
        """LOSS_AVERSION_LAMBDA は 2.25 (Kahneman & Tversky) であること"""
        assert LOSS_AVERSION_LAMBDA == pytest.approx(2.25)

    def test_event_decay_tau1(self):
        """EVENT_DECAY_TAU1 は 0.5 であること（高速減衰相）"""
        assert EVENT_DECAY_TAU1 == pytest.approx(0.5)

    def test_event_decay_tau2(self):
        """EVENT_DECAY_TAU2 は 4.0 であること（低速減衰相）"""
        assert EVENT_DECAY_TAU2 == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# テスト 1: compute_exposure() — 属性別曝露確率
# ---------------------------------------------------------------------------


class TestComputeExposure:
    """情報源が一致するエージェントは曝露確率が高い。
    Openness が高いほど新規ソースへの曝露確率も高い。
    """

    def test_exposure_range(self):
        """曝露確率は [0, 1] の範囲に収まること"""
        agent = _make_agent(0)
        event = _make_event()
        prob = compute_exposure(agent, event)
        assert 0.0 <= prob <= 1.0

    def test_matching_source_higher_exposure(self):
        """情報源が一致するエージェントは不一致より曝露確率が高いこと"""
        matching_agent = _make_agent(0, information_source="テレビニュース")
        unmatching_agent = _make_agent(1, information_source="専門誌")
        event = _make_event(source="テレビニュース")

        p_match = compute_exposure(matching_agent, event)
        p_unmatch = compute_exposure(unmatching_agent, event)
        assert p_match > p_unmatch

    def test_high_openness_increases_exposure(self):
        """高 Openness のエージェントは異質な情報源でも曝露確率が上がること"""
        low_o = _make_agent(0, information_source="専門誌", openness=0.1)
        high_o = _make_agent(1, information_source="専門誌", openness=0.9)
        event = _make_event(source="SNS(Twitter/X)")

        p_low = compute_exposure(low_o, event)
        p_high = compute_exposure(high_o, event)
        assert p_high > p_low

    def test_sns_source_higher_baseline(self):
        """SNS を情報源とするエージェントは全体的に曝露確率が高いこと（アルゴリズム推薦）"""
        sns_agent = _make_agent(0, information_source="SNS(Twitter/X)")
        newspaper_agent = _make_agent(1, information_source="新聞")
        event = _make_event(source="SNS(Twitter/X)")

        p_sns = compute_exposure(sns_agent, event)
        p_news = compute_exposure(newspaper_agent, event)
        assert p_sns > p_news


# ---------------------------------------------------------------------------
# テスト 2: compute_trust() — 情報源信頼度
# ---------------------------------------------------------------------------


class TestComputeTrust:
    """情報源の信頼度は [0, 1] で返される。
    エージェントの主要情報源と一致する場合に信頼度が高くなる。
    """

    def test_trust_range(self):
        """信頼度は [0, 1] の範囲に収まること"""
        agent = _make_agent(0, information_source="NHK")
        trust = compute_trust(agent, source="NHK")
        assert 0.0 <= trust <= 1.0

    def test_matching_source_higher_trust(self):
        """普段使っている情報源への信頼度は知らない情報源より高いこと"""
        agent = _make_agent(0, information_source="NHK")
        trust_own = compute_trust(agent, source="NHK")
        trust_other = compute_trust(agent, source="SNS(Twitter/X)")
        assert trust_own > trust_other

    def test_nhk_higher_trust_than_sns(self):
        """NHK への信頼度は SNS より高いこと（デフォルトエージェント）"""
        agent = _make_agent(0, information_source="テレビニュース")
        trust_nhk = compute_trust(agent, source="NHK")
        trust_sns = compute_trust(agent, source="SNS(Twitter/X)")
        assert trust_nhk > trust_sns

    def test_unknown_source_returns_nonzero(self):
        """未知の情報源でも 0 より大きい信頼度が返ること"""
        agent = _make_agent(0)
        trust = compute_trust(agent, source="存在しない情報源")
        assert trust > 0.0


# ---------------------------------------------------------------------------
# テスト 3: compute_interpretation() — 解釈方向
# ---------------------------------------------------------------------------


class TestComputeInterpretation:
    """positive framing のイベントは賛成寄りのエージェントが +1 に解釈。
    negative framing のイベントは反対寄りのエージェントが +1 に解釈。
    """

    def test_direction_is_plus1_or_minus1(self):
        """返値は +1 か -1 であること"""
        agent = _make_agent(0, opinion=0.7)
        event = _make_event(framing="positive")
        direction = compute_interpretation(agent, event)
        assert direction in (1, -1)

    def test_positive_framing_pro_agent_positive_direction(self):
        """positive framing × 賛成エージェント（opinion > 0.5）→ direction = +1"""
        agent = _make_agent(0, opinion=0.8)
        event = _make_event(framing="positive")
        direction = compute_interpretation(agent, event)
        assert direction == 1

    def test_positive_framing_con_agent_negative_direction(self):
        """positive framing × 反対エージェント（opinion < 0.5）→ direction = -1"""
        agent = _make_agent(0, opinion=0.2)
        event = _make_event(framing="positive")
        direction = compute_interpretation(agent, event)
        assert direction == -1

    def test_negative_framing_flips_direction(self):
        """negative framing は方向を逆転させること"""
        agent = _make_agent(0, opinion=0.8)
        positive_event = _make_event(framing="positive")
        negative_event = _make_event(framing="negative")
        d_pos = compute_interpretation(agent, positive_event)
        d_neg = compute_interpretation(agent, negative_event)
        assert d_pos == -d_neg

    def test_neutral_agent_framing_determines_direction(self):
        """中立エージェント（opinion=0.5）は framing で方向が決まること"""
        agent = _make_agent(0, opinion=0.5)
        pos_event = _make_event(framing="positive")
        neg_event = _make_event(framing="negative")
        d_pos = compute_interpretation(agent, pos_event)
        d_neg = compute_interpretation(agent, neg_event)
        assert d_pos == 1
        assert d_neg == -1


# ---------------------------------------------------------------------------
# テスト 4: Prospect Theory 非対称テスト
# ---------------------------------------------------------------------------


class TestProspectTheory:
    """negative direction の delta は positive の LOSS_AVERSION_LAMBDA=2.25 倍になること。
    対称モード（prospect_theory=False）では倍率が適用されないこと。
    """

    def test_loss_larger_than_gain(self):
        """同じ magnitude で、損失（direction=-1）は利得（direction=+1）の約 2.25 倍"""
        magnitude = 0.05  # small enough to avoid tanh clipping
        delta_gain = compute_event_delta(magnitude, direction=1, prospect_theory=True)
        delta_loss = compute_event_delta(magnitude, direction=-1, prospect_theory=True)

        # gain → positive delta, loss → negative delta
        assert delta_gain > 0
        assert delta_loss < 0
        ratio = abs(delta_loss) / abs(delta_gain)
        assert ratio == pytest.approx(LOSS_AVERSION_LAMBDA, rel=0.05), (
            f"損失倍率 {ratio:.3f} が LOSS_AVERSION_LAMBDA={LOSS_AVERSION_LAMBDA} と乖離"
        )

    def test_symmetric_mode_no_lambda(self):
        """prospect_theory=False ではゲインと損失の大きさが等しいこと"""
        magnitude = 0.05
        delta_gain = compute_event_delta(magnitude, direction=1, prospect_theory=False)
        delta_loss = compute_event_delta(magnitude, direction=-1, prospect_theory=False)
        assert abs(delta_gain) == pytest.approx(abs(delta_loss), rel=1e-6)

    def test_gain_direction_positive(self):
        """direction=+1 の delta は正であること"""
        delta = compute_event_delta(0.1, direction=1)
        assert delta > 0

    def test_loss_direction_negative(self):
        """direction=-1 の delta は負であること"""
        delta = compute_event_delta(0.1, direction=-1)
        assert delta < 0


# ---------------------------------------------------------------------------
# テスト 5: tanh 飽和テスト
# ---------------------------------------------------------------------------


class TestTanhSaturation:
    """magnitude が非常に大きくても出力が MAX_EVENT_DELTA を超えないこと。"""

    def test_large_magnitude_capped(self):
        """magnitude=100 でも |delta| <= MAX_EVENT_DELTA"""
        delta = compute_event_delta(100.0, direction=1)
        assert abs(delta) <= MAX_EVENT_DELTA + 1e-9

    def test_large_loss_magnitude_capped(self):
        """magnitude=100, direction=-1 でも |delta| <= MAX_EVENT_DELTA"""
        delta = compute_event_delta(100.0, direction=-1)
        assert abs(delta) <= MAX_EVENT_DELTA + 1e-9

    def test_zero_magnitude_zero_delta(self):
        """magnitude=0 → delta=0"""
        delta = compute_event_delta(0.0, direction=1)
        assert delta == pytest.approx(0.0)

    def test_output_monotone_in_magnitude(self):
        """magnitude が大きいほど |delta| が大きくなること（飽和前）"""
        d1 = abs(compute_event_delta(0.05, direction=1))
        d2 = abs(compute_event_delta(0.10, direction=1))
        d3 = abs(compute_event_delta(0.20, direction=1))
        assert d1 < d2 < d3

    def test_prospect_theory_loss_also_capped(self):
        """Prospect Theory 適用後の損失も MAX_EVENT_DELTA に収まること"""
        # 損失は magnitude * LAMBDA で増幅されるが tanh で飽和するはず
        delta = compute_event_delta(0.5, direction=-1, prospect_theory=True)
        assert abs(delta) <= MAX_EVENT_DELTA + 1e-9


# ---------------------------------------------------------------------------
# テスト 6: Two-phase event decay テスト
# ---------------------------------------------------------------------------


class TestTwoPhaseDEcay:
    """event_residual(raw_delta, steps_elapsed) が二段階指数減衰を実装すること。

    r(t) = raw_delta * (0.5 * exp(-t / TAU1) + 0.5 * exp(-t / TAU2))

    TAU1=0.5 → 高速減衰（短期）
    TAU2=4.0 → 低速減衰（長期）
    """

    def test_residual_at_zero_steps_equals_raw(self):
        """t=0 での残留効果は raw_delta と等しいこと"""
        raw = 0.2
        r = event_residual(raw, steps_elapsed=0)
        assert r == pytest.approx(raw, rel=1e-6)

    def test_residual_decays_over_time(self):
        """時間が経つほど残留効果が減衰すること"""
        raw = 0.3
        r0 = event_residual(raw, steps_elapsed=0)
        r1 = event_residual(raw, steps_elapsed=1)
        r5 = event_residual(raw, steps_elapsed=5)
        assert r0 > r1 > r5 > 0

    def test_fast_phase_dominant_early(self):
        """TAU1=0.5 の高速相が初期で支配的であること（t=1 で大幅に減衰）"""
        raw = 1.0
        r1 = event_residual(raw, steps_elapsed=1)
        # t=1 では fast phase (exp(-1/0.5)=exp(-2)≈0.135) + slow phase (exp(-1/4)≈0.779)
        # 合計: 0.5 * 0.135 + 0.5 * 0.779 ≈ 0.457
        expected = 0.5 * math.exp(-1 / EVENT_DECAY_TAU1) + 0.5 * math.exp(-1 / EVENT_DECAY_TAU2)
        assert r1 == pytest.approx(expected * raw, rel=1e-5)

    def test_slow_phase_dominant_late(self):
        """TAU2=4.0 の低速相が長期で支配的であること（t=10 で fast phase はほぼ 0）"""
        raw = 1.0
        r10 = event_residual(raw, steps_elapsed=10)
        # t=10: fast=0.5*exp(-20)≈0, slow=0.5*exp(-2.5)≈0.041
        fast_contribution = 0.5 * math.exp(-10 / EVENT_DECAY_TAU1)
        slow_contribution = 0.5 * math.exp(-10 / EVENT_DECAY_TAU2)
        assert fast_contribution < slow_contribution * 0.01  # fast はほぼ無視できる

    def test_two_phase_formula(self):
        """任意の t で公式 r(t) = raw * (0.5*exp(-t/TAU1) + 0.5*exp(-t/TAU2)) が成立すること"""
        raw = 0.25
        for t in [0, 1, 2, 5, 10]:
            expected = raw * (
                0.5 * math.exp(-t / EVENT_DECAY_TAU1) + 0.5 * math.exp(-t / EVENT_DECAY_TAU2)
            )
            actual = event_residual(raw, steps_elapsed=t)
            assert actual == pytest.approx(expected, rel=1e-6), f"t={t}: {actual} != {expected}"

    def test_negative_delta_preserves_sign(self):
        """raw_delta が負でも符号を保ちながら減衰すること"""
        raw = -0.2
        r = event_residual(raw, steps_elapsed=1)
        assert r < 0

    def test_residual_sign_preserved_at_any_t(self):
        """残留効果の符号は常に raw_delta と同じであること"""
        raw = 0.15
        for t in [0, 1, 3, 10]:
            r = event_residual(raw, steps_elapsed=t)
            assert r >= 0, f"t={t} で符号が反転"


# ---------------------------------------------------------------------------
# テスト 7: アブレーション 4 条件の差異テスト
# ---------------------------------------------------------------------------


class TestAblations:
    """4 つのアブレーション関数がそれぞれ異なる挙動を示すこと。

    1. ablation_no_event          → event_delta = 0 (常に)
    2. ablation_uniform_exposure  → 全エージェントが同一曝露確率
    3. ablation_heterogeneous_exposure → 属性差異を反映した曝露確率
    4. ablation_symmetric_event   → Prospect Theory 無効 (direction 倍率なし)
    """

    def _make_agents_and_event(self):
        agents = [
            _make_agent(0, information_source="SNS(Twitter/X)", openness=0.9),
            _make_agent(1, information_source="新聞", openness=0.2),
            _make_agent(2, information_source="NHK", openness=0.5),
        ]
        event = _make_event(source="SNS(Twitter/X)", framing="negative", magnitude=0.15)
        return agents, event

    def test_no_event_returns_zero_deltas(self):
        """ablation_no_event は全エージェントで delta=0 を返すこと"""
        agents, event = self._make_agents_and_event()
        deltas = ablation_no_event(agents, event)
        assert all(d == 0.0 for d in deltas), f"no_event で delta≠0: {deltas}"

    def test_uniform_exposure_same_for_all(self):
        """ablation_uniform_exposure は全エージェントで同一の曝露確率を使用すること"""
        agents, event = self._make_agents_and_event()
        deltas = ablation_uniform_exposure(agents, event)
        # 曝露確率が全員同じなので絶対値が等しい (向きは解釈方向による)
        magnitudes = [abs(d) for d in deltas]
        assert magnitudes[0] == pytest.approx(magnitudes[1], rel=1e-6)
        assert magnitudes[1] == pytest.approx(magnitudes[2], rel=1e-6)

    def test_heterogeneous_exposure_varies(self):
        """ablation_heterogeneous_exposure は属性によって delta が異なること"""
        agents, event = self._make_agents_and_event()
        deltas = ablation_heterogeneous_exposure(agents, event)
        magnitudes = [abs(d) for d in deltas]
        # SNS ユーザー（agent-0）と新聞ユーザー（agent-1）で差があること
        assert magnitudes[0] != pytest.approx(magnitudes[1], rel=1e-6)

    def test_symmetric_no_lambda(self):
        """ablation_symmetric_event では +/- 方向で大きさが等しいこと"""
        positive_agent = _make_agent(0, opinion=0.8, information_source="テレビニュース")
        negative_agent = _make_agent(1, opinion=0.2, information_source="テレビニュース")

        pos_event = _make_event(framing="positive", magnitude=0.05)
        neg_event = _make_event(framing="positive", magnitude=0.05)

        # positive_agent は positive framing を +1 に解釈、negative_agent は -1 に解釈
        deltas_pos = ablation_symmetric_event([positive_agent], pos_event)
        deltas_neg = ablation_symmetric_event([negative_agent], neg_event)

        # 対称モード: |delta| が等しい（Prospect Theory 無効）
        assert abs(deltas_pos[0]) == pytest.approx(abs(deltas_neg[0]), rel=1e-6)

    def test_heterogeneous_differs_from_uniform(self):
        """異質曝露と均一曝露では delta の合計が異なること"""
        agents, event = self._make_agents_and_event()
        uniform = ablation_uniform_exposure(agents, event)
        hetero = ablation_heterogeneous_exposure(agents, event)
        # 少なくとも一エージェントで差があること
        diffs = [abs(u - h) for u, h in zip(uniform, hetero)]
        assert any(d > 1e-9 for d in diffs), "均一曝露と異質曝露が全く同じ"

    def test_no_event_differs_from_others(self):
        """no_event アブレーションは uniform/heterogeneous と必ず異なること"""
        agents, event = self._make_agents_and_event()
        no_event = ablation_no_event(agents, event)
        uniform = ablation_uniform_exposure(agents, event)
        # uniform が全員 0 でない場合（magnitude>0 なら必ず差が生じる）
        if any(d != 0.0 for d in uniform):
            assert no_event != uniform
