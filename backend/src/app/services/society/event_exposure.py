"""Event Exposure Model: 外部イベント注入の計算モジュール。

外部イベントが各エージェントに与える delta を 3 段階で計算する:
    1. compute_exposure()     — 情報源 × 属性 → 曝露確率
    2. compute_trust()        — 情報源信頼度
    3. compute_interpretation() — 解釈方向（+1 / -1）
    4. compute_event_delta()  — Prospect Theory 非対称 + tanh 飽和
    5. event_residual()       — Two-phase Decay（残留効果）

アブレーション 4 条件:
    - ablation_no_event()            : event_delta = 0 (常に)
    - ablation_uniform_exposure()    : 全エージェントが同一曝露確率
    - ablation_heterogeneous_exposure(): 属性差異を反映した曝露確率（通常モード）
    - ablation_symmetric_event()     : Prospect Theory 無効

References:
    - Kahneman & Tversky (1979): Prospect Theory, LOSS_AVERSION_LAMBDA = 2.25
    - Bordignon et al. (2021): Two-phase event decay in opinion models
"""

from __future__ import annotations

import math

from src.app.services.society.opinion_dynamics import MAX_EVENT_DELTA


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

#: Prospect Theory の損失回避係数（Kahneman & Tversky 1979）
LOSS_AVERSION_LAMBDA: float = 2.25

#: Two-phase decay の高速相時定数（短期記憶）
EVENT_DECAY_TAU1: float = 0.5

#: Two-phase decay の低速相時定数（長期記憶）
EVENT_DECAY_TAU2: float = 4.0

# 情報源のリーチスコア（高い = 広いリーチ = 曝露確率が高い）
_SOURCE_REACH_SCORES: dict[str, float] = {
    "SNS(Twitter/X)": 0.90,
    "SNS(Instagram)": 0.85,
    "YouTube": 0.80,
    "LINE NEWS": 0.75,
    "Yahoo!ニュース": 0.70,
    "テレビニュース": 0.65,
    "NHK": 0.65,
    "ポッドキャスト": 0.55,
    "口コミ・友人": 0.50,
    "職場の同僚": 0.45,
    "家族": 0.45,
    "地域コミュニティ": 0.40,
    "新聞": 0.35,
    "専門誌": 0.20,
}

# 情報源の信頼度スコア（高い = 信頼性が高い）
_SOURCE_TRUST_SCORES: dict[str, float] = {
    "NHK": 0.85,
    "新聞": 0.80,
    "専門誌": 0.85,
    "テレビニュース": 0.70,
    "Yahoo!ニュース": 0.60,
    "LINE NEWS": 0.55,
    "地域コミュニティ": 0.55,
    "口コミ・友人": 0.55,
    "家族": 0.60,
    "職場の同僚": 0.55,
    "ポッドキャスト": 0.50,
    "YouTube": 0.45,
    "SNS(Instagram)": 0.40,
    "SNS(Twitter/X)": 0.35,
}

_DEFAULT_REACH: float = 0.50
_DEFAULT_TRUST: float = 0.50


# ---------------------------------------------------------------------------
# 主要計算関数
# ---------------------------------------------------------------------------


def compute_exposure(agent: dict, event: dict) -> float:
    """情報源 × 属性からエージェントの曝露確率を計算する。

    情報源が一致するほど曝露確率が高く、
    高 Openness のエージェントは異質な情報源にも曝露されやすい。

    計算式:
        base = reach_score(event.source)
        match_bonus = 0.2 if agent.information_source == event.source else 0.0
        openness_bonus = 0.1 * openness_i  (Openness が高いと+)
        exposure = clip(base + match_bonus + openness_bonus, 0, 1)

    Args:
        agent: エージェント dict（information_source, big_five.O を含む）
        event: イベント dict（source を含む）

    Returns:
        曝露確率 [0, 1]
    """
    event_source = event.get("source", "")
    agent_source = agent.get("information_source", "")
    openness = agent.get("big_five", {}).get("O", 0.5)

    base = _SOURCE_REACH_SCORES.get(event_source, _DEFAULT_REACH)
    match_bonus = 0.2 if agent_source == event_source else 0.0
    openness_bonus = 0.1 * openness

    return float(min(1.0, max(0.0, base + match_bonus + openness_bonus)))


def compute_trust(agent: dict, source: str) -> float:
    """エージェントの情報源信頼度を計算する。

    エージェントの主要情報源と一致する場合はボーナスを追加する。

    計算式:
        base = trust_score(source)
        match_bonus = 0.15 if agent.information_source == source else 0.0
        trust = clip(base + match_bonus, 0, 1)

    Args:
        agent: エージェント dict（information_source を含む）
        source: 評価対象の情報源名

    Returns:
        信頼度 [0, 1]
    """
    agent_source = agent.get("information_source", "")
    base = _SOURCE_TRUST_SCORES.get(source, _DEFAULT_TRUST)
    match_bonus = 0.15 if agent_source == source else 0.0

    return float(min(1.0, max(0.0, base + match_bonus)))


def compute_interpretation(agent: dict, event: dict) -> int:
    """エージェントがイベントをどの方向に解釈するかを返す。

    positive framing のイベント:
        - opinion > 0.5 （賛成寄り）→ +1（肯定的に受け取る）
        - opinion <= 0.5（反対寄り）→ -1（脅威と受け取る）

    negative framing のイベント: 上記の逆

    中立エージェント（opinion == 0.5）は framing が positive なら +1、negative なら -1。

    Args:
        agent: エージェント dict（opinion_vector を含む）
        event: イベント dict（framing を含む）

    Returns:
        解釈方向 +1 または -1
    """
    opinion = agent.get("opinion_vector", [0.5])[0]
    framing = event.get("framing", "positive")

    # opinion が 0.5 より大きければ賛成寄り → positive framing は +1
    # opinion が 0.5 以下なら反対寄り → positive framing は -1
    aligned = opinion >= 0.5

    if framing == "positive":
        return 1 if aligned else -1
    else:  # negative or other
        return -1 if aligned else 1


def compute_event_delta(
    magnitude: float,
    direction: int,
    prospect_theory: bool = True,
) -> float:
    """外部イベントによる意見変化量を計算する。

    Prospect Theory 非対称:
        direction = -1（損失） → magnitude に LOSS_AVERSION_LAMBDA を乗算
        direction = +1（利得） → magnitude をそのまま使用

    tanh 飽和（Step 8 の _apply_event_delta_tanh と同じ式）:
        delta = MAX_EVENT_DELTA * tanh(effective_magnitude / MAX_EVENT_DELTA) * sign(direction)

    Args:
        magnitude: 非負のイベント強度
        direction: +1（利得方向）または -1（損失方向）
        prospect_theory: True の場合 Prospect Theory 適用（デフォルト）

    Returns:
        飽和した delta [-MAX_EVENT_DELTA, MAX_EVENT_DELTA]
    """
    effective_magnitude = magnitude
    if prospect_theory and direction == -1:
        effective_magnitude = magnitude * LOSS_AVERSION_LAMBDA

    saturated = MAX_EVENT_DELTA * math.tanh(effective_magnitude / MAX_EVENT_DELTA)
    return saturated * (1.0 if direction >= 0 else -1.0)


def event_residual(raw_delta: float, steps_elapsed: int) -> float:
    """Two-phase exponential decay で残留イベント効果を計算する。

    公式:
        r(t) = raw_delta * (0.5 * exp(-t / TAU1) + 0.5 * exp(-t / TAU2))

    TAU1=0.5（高速相: ニュースの即時効果）
    TAU2=4.0（低速相: 長期的な影響の残留）

    Args:
        raw_delta: 初期イベント delta
        steps_elapsed: イベント発生からの経過ステップ数

    Returns:
        残留 delta（raw_delta と同符号）
    """
    t = steps_elapsed
    weight = 0.5 * math.exp(-t / EVENT_DECAY_TAU1) + 0.5 * math.exp(-t / EVENT_DECAY_TAU2)
    return raw_delta * weight


# ---------------------------------------------------------------------------
# アブレーション 4 条件
# ---------------------------------------------------------------------------


def ablation_no_event(agents: list[dict], event: dict) -> list[float]:
    """アブレーション条件 1: イベントなし。

    全エージェントの delta を 0 にする。

    Args:
        agents: エージェントリスト
        event: イベント dict（使用しない）

    Returns:
        全要素 0.0 のリスト
    """
    return [0.0] * len(agents)


def ablation_uniform_exposure(agents: list[dict], event: dict) -> list[float]:
    """アブレーション条件 2: 均一曝露。

    全エージェントが同じ曝露確率（0.5）・同じ信頼度（0.5）を使用する。
    Prospect Theory は通常通り適用。

    Args:
        agents: エージェントリスト
        event: イベント dict

    Returns:
        各エージェントの event_delta リスト（|delta| は全員等しい）
    """
    magnitude = event.get("magnitude", 0.1)
    uniform_exposure = 0.5
    uniform_trust = 0.5

    deltas = []
    for agent in agents:
        direction = compute_interpretation(agent, event)
        effective_mag = magnitude * uniform_exposure * uniform_trust
        delta = compute_event_delta(effective_mag, direction, prospect_theory=True)
        deltas.append(delta)
    return deltas


def ablation_heterogeneous_exposure(agents: list[dict], event: dict) -> list[float]:
    """アブレーション条件 3: 異質曝露（通常モード）。

    属性別に曝露確率・信頼度が異なる。
    Prospect Theory は通常通り適用。

    Args:
        agents: エージェントリスト
        event: イベント dict

    Returns:
        各エージェントの event_delta リスト
    """
    magnitude = event.get("magnitude", 0.1)

    deltas = []
    for agent in agents:
        exposure = compute_exposure(agent, event)
        trust = compute_trust(agent, event.get("source", ""))
        direction = compute_interpretation(agent, event)
        effective_mag = magnitude * exposure * trust
        delta = compute_event_delta(effective_mag, direction, prospect_theory=True)
        deltas.append(delta)
    return deltas


def ablation_symmetric_event(agents: list[dict], event: dict) -> list[float]:
    """アブレーション条件 4: 対称イベント（Prospect Theory 無効）。

    損失・利得に非対称性をかけない（direction 倍率なし）。
    属性別曝露確率は通常通り適用。

    Args:
        agents: エージェントリスト
        event: イベント dict

    Returns:
        各エージェントの event_delta リスト（損失・利得が等大きさ）
    """
    magnitude = event.get("magnitude", 0.1)

    deltas = []
    for agent in agents:
        exposure = compute_exposure(agent, event)
        trust = compute_trust(agent, event.get("source", ""))
        direction = compute_interpretation(agent, event)
        effective_mag = magnitude * exposure * trust
        delta = compute_event_delta(effective_mag, direction, prospect_theory=False)
        deltas.append(delta)
    return deltas
