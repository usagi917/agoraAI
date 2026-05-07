"""Opinion Dynamics Engine: Bounded Confidence (Hegselmann-Krause) + Friedkin-Johnsen.

Implements network-based opinion propagation where agents update their opinions
based on neighbors within a confidence threshold, anchored by individual stubbornness.

Mathematical model per agent i at timestep t:
    x_i(t+1) = s_i * memory_anchor_i + (1 - s_i) * biased_neighbor_mean(neighbors)

Where:
    s_i = stubbornness (derived from Big Five C: 0.4 + 0.45 * C)
    neighbors = {j in N_i : ||x_j(t) - x_i(t)|| < confidence_threshold}
    biased_neighbor_mean uses confirmation-bias-weighted edge strengths
    memory_anchor_i = exponentially decayed mean of recent opinion history (FJ-MM)

Update phases per timestep (applied in order):
    1. External event injection  (event_delta via tanh saturation)
    2. Conversation / propagation (HK + FJ with memory anchor + confirmation bias)
    3. Belief decay               (opinion drifts back toward memory anchor)

References:
    - Hegselmann & Krause (2002): Opinion Dynamics and Bounded Confidence
    - Friedkin & Johnsen (1990): Social Influence and Opinions
    - FJ-MM (arXiv:2504.06731, 2025): Memory effects in opinion dynamics
    - Gestefeld & Lorenz (2023, JASSS): Motivated cognition / confirmation bias
    - Dyer et al. (2024, JEDC): Bayesian Optimization for ABM parameter estimation
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import optuna
from sklearn.cluster import DBSCAN

optuna.logging.set_verbosity(optuna.logging.WARNING)

# ---------------------------------------------------------------------------
# Step 8 constants
# ---------------------------------------------------------------------------

#: Maximum opinion shift per conversation step (clamp)
MAX_CONV_DELTA: float = 0.15

#: Maximum opinion shift from external event (tanh saturation upper bound)
MAX_EVENT_DELTA: float = 0.25

#: Base belief decay rate per step (opinion drifts back toward memory anchor)
BASE_DECAY: float = 0.02

#: Number of past steps used in FJ-MM memory anchor
MEMORY_WINDOW: int = 4

#: Exponential decay rate for memory anchor weights (k=0 is most recent)
MEMORY_DECAY: float = 0.3

#: Confirmation bias strength (same-direction neighbor weight amplifier)
CONFIRMATION_BIAS: float = 0.3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PropagationStepResult:
    updated_opinions: list[list[float]]
    max_delta: float
    timestep: int


@dataclass
class ClusterInfo:
    label: int
    member_ids: list[str]
    centroid: list[float]
    size: int


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def stubbornness_from_big_five(
    conscientiousness: float,
    agreeableness: float = 0.5,
) -> float:
    """Derive stubbornness from Big Five Conscientiousness and Agreeableness scores.

    s = 0.4 + 0.45 * C - 0.1 * A, clamped to [0.3, 0.85].
    Higher C preserves stronger initial convictions.
    Higher A slightly reduces stubbornness (more receptive to others).
    """
    s = 0.4 + 0.45 * conscientiousness - 0.1 * agreeableness
    return max(0.3, min(0.85, s))


def compute_heterogeneous_thresholds(
    agents: list[dict],
    base_epsilon: float = 0.3,
    alpha: float = 0.15,
    beta: float = 0.05,
    gamma: float = 0.0,
    noise_sigma: float = 0.02,
    seed: int | None = None,
) -> list[float]:
    """Compute per-agent confidence thresholds from Big Five traits.

    Formula: epsilon_i = base_epsilon + alpha*(1-C_i) + beta*(1-O_i) + gamma*A_i + N(0, sigma^2)

    - Higher C (Conscientiousness) -> narrower threshold (more committed)
    - Higher O (Openness) -> narrower threshold (more discerning)
    - Higher A (Agreeableness) -> wider threshold (more receptive to others)

    Args:
        agents: Agent dicts with big_five.{C, O, A}.
        base_epsilon: Base confidence threshold.
        alpha: Weight for Conscientiousness effect (inverted).
        beta: Weight for Openness effect (inverted).
        gamma: Weight for Agreeableness effect (direct).
        noise_sigma: Standard deviation of Gaussian noise.
        seed: Random seed for reproducibility.

    Returns:
        List of per-agent confidence thresholds.
    """
    rng = np.random.default_rng(seed)
    thresholds: list[float] = []

    for agent in agents:
        big_five = agent.get("big_five", {})
        c_val = big_five.get("C", 0.5)
        o_val = big_five.get("O", 0.5)
        a_val = big_five.get("A", 0.5)

        eps = base_epsilon + alpha * (1 - c_val) + beta * (1 - o_val) + gamma * a_val
        if noise_sigma > 0:
            eps += rng.normal(0, noise_sigma)
        # Clamp to reasonable range
        eps = max(0.05, min(1.0, eps))
        thresholds.append(eps)

    return thresholds


# 情報源のフィルターバブル傾向スコア（高い = バブル傾向が強い = 閾値が狭い）
_SOURCE_BUBBLE_SCORES: dict[str, float] = {
    "SNS(Twitter/X)": 0.85,
    "SNS(Instagram)": 0.80,
    "YouTube": 0.70,
    "LINE NEWS": 0.60,
    "ポッドキャスト": 0.55,
    "Yahoo!ニュース": 0.50,
    "口コミ・友人": 0.50,
    "職場の同僚": 0.45,
    "家族": 0.45,
    "地域コミュニティ": 0.40,
    "テレビニュース": 0.30,
    "NHK": 0.25,
    "新聞": 0.20,
    "専門誌": 0.15,
}


def compute_filter_bubble_thresholds(
    agents: list[dict],
    base_epsilon: float | None = None,
    bubble_weight: float | None = None,
    openness_mitigation: float = 0.1,
    agreeableness_mitigation: float = 0.08,
    *,
    base_threshold: float | None = None,
    bubble_width: float | None = None,
) -> np.ndarray:
    """Compute confidence thresholds adjusted for information source filter bubbles.

    High bubble_score sources (e.g. algorithmic social media) narrow the threshold,
    simulating echo chamber effects. Openness and Agreeableness mitigate this effect.

    Supports both new-style agents (information_sources: list[dict] with bubble_score)
    and legacy agents (information_source: str looked up in _SOURCE_BUBBLE_SCORES).

    Args:
        agents: Agent dicts with big_five.{O, A} and information_sources or information_source.
        base_epsilon / base_threshold: Base confidence threshold (default 0.3).
        bubble_weight / bubble_width: How much bubble_score narrows the threshold (default 0.15).
        openness_mitigation: How much Openness counteracts the bubble.
        agreeableness_mitigation: How much Agreeableness counteracts the bubble.

    Returns:
        ndarray of per-agent confidence thresholds.
    """
    # Backward-compatible parameter aliases
    base_eps = base_epsilon if base_epsilon is not None else (base_threshold if base_threshold is not None else 0.3)
    bw = bubble_weight if bubble_weight is not None else (bubble_width if bubble_width is not None else 0.15)

    thresholds = np.empty(len(agents), dtype=np.float64)

    for i, agent in enumerate(agents):
        if bw == 0.0:
            thresholds[i] = base_eps
            continue

        big_five = agent.get("big_five", {})
        o_val = big_five.get("O", 0.5)
        a_val = big_five.get("A", 0.5)

        # New format: information_sources as list of dicts with bubble_score
        sources = agent.get("information_sources", [])
        if sources:
            avg_bubble = sum(s.get("bubble_score", 0.0) for s in sources) / len(sources)
        else:
            # Legacy format: information_source as string
            source_str = agent.get("information_source", "")
            if source_str:
                raw_bubble = _SOURCE_BUBBLE_SCORES.get(source_str, 0.5)
                avg_bubble = raw_bubble * (1.0 - 0.5 * o_val)
            else:
                avg_bubble = 0.0

        # Bubble narrows threshold; O and A mitigate
        bubble_effect = bw * avg_bubble
        mitigation = openness_mitigation * o_val + agreeableness_mitigation * a_val
        eps = base_eps - bubble_effect + mitigation

        thresholds[i] = max(0.05, min(1.0, eps))

    return thresholds


# ---------------------------------------------------------------------------
# Step 8: New standalone helper functions
# ---------------------------------------------------------------------------


def apply_belief_decay(current: float, initial: float) -> float:
    """Apply one step of belief decay toward the initial (anchor) opinion.

    The opinion drifts back toward *initial* by BASE_DECAY fraction of the gap:
        new = current - BASE_DECAY * (current - initial)
           = (1 - BASE_DECAY) * current + BASE_DECAY * initial

    Args:
        current: Current opinion value in [0, 1].
        initial: Initial (anchor) opinion value in [0, 1].

    Returns:
        Decayed opinion value.
    """
    return current - BASE_DECAY * (current - initial)


def compute_memory_anchor(
    opinion_history: list[float],
    initial_opinion: float,
) -> float:
    """Compute the FJ-MM memory anchor from recent opinion history.

    Uses the last MEMORY_WINDOW steps with exponential decay weights:
        weight_k = exp(-MEMORY_DECAY * k)   where k=0 is the most recent step.

    If history has <= 1 entries (only initial), returns initial_opinion directly.

    Args:
        opinion_history: List of past opinion values (oldest first, most recent last).
        initial_opinion: The agent's initial opinion (used as fallback).

    Returns:
        Weighted average anchor opinion.
    """
    if len(opinion_history) <= 1:
        return initial_opinion

    # Take the last MEMORY_WINDOW values
    window = opinion_history[-MEMORY_WINDOW:]

    # k=0 is the most recent (last element), k=len-1 is oldest in window
    weights = [math.exp(-MEMORY_DECAY * k) for k in range(len(window))]
    total = sum(weights)

    # reversed(window): window[-1] (most recent) gets weight k=0
    anchor = sum(w * o for w, o in zip(weights, reversed(window))) / total
    return anchor


def compute_confirmation_bias_weight(
    agent_opinion: float,
    neighbor_opinion: float,
    base_weight: float,
) -> float:
    """Compute the confirmation-bias-adjusted neighbor weight.

    Amplifies same-direction neighbors by (1 + CONFIRMATION_BIAS),
    attenuates opposite-direction by (1 - CONFIRMATION_BIAS * 0.5).
    Neutral agents (opinion == 0.5) receive no bias.

    Direction is determined relative to the midpoint 0.5:
        same direction   if (neighbor - agent) * (agent - 0.5) > 0
        opposite direction if (neighbor - agent) * (agent - 0.5) < 0

    Args:
        agent_opinion: The agent's current opinion in [0, 1].
        neighbor_opinion: The neighbor's current opinion in [0, 1].
        base_weight: The raw edge weight.

    Returns:
        Bias-adjusted weight.
    """
    if abs(agent_opinion - 0.5) < 1e-9:
        # Neutral agent: no bias
        return base_weight

    same_direction = (neighbor_opinion - agent_opinion) * (agent_opinion - 0.5) > 0
    if same_direction:
        return base_weight * (1.0 + CONFIRMATION_BIAS)
    else:
        return base_weight * (1.0 - CONFIRMATION_BIAS * 0.5)


def _apply_event_delta_tanh(magnitude: float, direction: int) -> float:
    """Apply tanh saturation to an event impact delta.

    The output is bounded by MAX_EVENT_DELTA:
        delta = MAX_EVENT_DELTA * tanh(magnitude / MAX_EVENT_DELTA) * sign(direction)

    Args:
        magnitude: Non-negative raw magnitude of the event impact.
        direction: +1 for positive direction, -1 for negative direction.

    Returns:
        Saturated delta in [-MAX_EVENT_DELTA, MAX_EVENT_DELTA].
    """
    delta = MAX_EVENT_DELTA * math.tanh(magnitude / MAX_EVENT_DELTA)
    return delta * math.copysign(1.0, direction)


def apply_three_phase_update(
    current_opinion: float,
    initial_opinion: float,
    event_delta: float,
    neighbor_mean: float,
    stubbornness: float,
    event_fn: Callable[[float, float], float] | None = None,
    conversation_fn: Callable[[float, float, float], float] | None = None,
    decay_fn: Callable[[float, float], float] | None = None,
) -> float:
    """Apply the three-phase opinion update in order: event → conversation → decay.

    Phase 1 (event): Skipped if event_delta == 0.
    Phase 2 (conversation): FJ-MM weighted neighbor mean.
    Phase 3 (decay): Belief decay toward initial opinion.

    Default implementations use module-level functions when callables are not provided.

    Args:
        current_opinion: Current opinion in [0, 1].
        initial_opinion: Initial anchor opinion in [0, 1].
        event_delta: External event delta (pre-computed, already tanh-saturated).
        neighbor_mean: Weighted mean of qualifying neighbors.
        stubbornness: Agent stubbornness s_i.
        event_fn: Optional override for event phase.
        conversation_fn: Optional override for conversation phase.
        decay_fn: Optional override for decay phase.

    Returns:
        Updated opinion in [0, 1].
    """
    opinion = current_opinion

    # Phase 1: External event injection (skip if no event)
    if event_delta != 0.0:
        if event_fn is not None:
            opinion = event_fn(opinion, event_delta)
        else:
            opinion = opinion + event_delta
        opinion = float(np.clip(opinion, 0.0, 1.0))

    # Phase 2: Conversation / propagation (FJ-MM)
    if conversation_fn is not None:
        opinion = conversation_fn(opinion, neighbor_mean, stubbornness)
    else:
        opinion = stubbornness * initial_opinion + (1.0 - stubbornness) * neighbor_mean

    opinion = float(np.clip(opinion, 0.0, 1.0))

    # Phase 3: Belief decay
    if decay_fn is not None:
        opinion = decay_fn(opinion, initial_opinion)
    else:
        opinion = apply_belief_decay(opinion, initial_opinion)

    return float(np.clip(opinion, 0.0, 1.0))


def optimize_opinion_dynamics_params(
    target_distribution: dict[str, float],
    initial_opinions: list[float],
    n_trials: int = 200,
    seed: int | None = None,
) -> tuple[dict, float]:
    """Optimize opinion dynamics parameters using Optuna TPE to minimize EMD.

    Explores:
        confidence_threshold in [0.05, 1.0]
        base_stubbornness in [0.1, 0.9]

    Args:
        target_distribution: The reference stance distribution to match.
        initial_opinions: Initial opinion values for a small simulated population.
        n_trials: Number of Optuna trials (default 200; use 50 for tests).
        seed: Random seed for reproducibility.

    Returns:
        (best_params dict, best_emd float)
    """
    from src.app.utils.distribution_metrics import earth_movers_distance

    _STANCE_THRESHOLDS_LOCAL: list[tuple[float, str]] = [
        (0.8, "賛成"),
        (0.6, "条件付き賛成"),
        (0.4, "中立"),
        (0.2, "条件付き反対"),
        (0.0, "反対"),
    ]

    def _opinion_to_stance(val: float) -> str:
        for threshold, label in _STANCE_THRESHOLDS_LOCAL:
            if val >= threshold:
                return label
        return "反対"

    def _simulate_and_compute_emd(confidence_threshold: float, base_stubbornness: float) -> float:
        n = len(initial_opinions)
        opinions = list(initial_opinions)

        # Build a ring topology for the mini simulation
        for _ in range(5):  # 5 timesteps
            new_opinions = []
            for i in range(n):
                s_i = base_stubbornness
                x_i = opinions[i]
                x_i_0 = initial_opinions[i]

                # Find qualifying neighbors
                neighbors = [opinions[j] for j in range(n) if j != i and abs(opinions[j] - x_i) <= confidence_threshold]
                if neighbors:
                    neighbor_mean = sum(neighbors) / len(neighbors)
                    new_x = s_i * x_i_0 + (1.0 - s_i) * neighbor_mean
                    delta = new_x - x_i
                    # Clamp to MAX_CONV_DELTA
                    if abs(delta) > MAX_CONV_DELTA:
                        delta = math.copysign(MAX_CONV_DELTA, delta)
                    new_x = x_i + delta
                else:
                    new_x = x_i
                new_opinions.append(float(np.clip(new_x, 0.0, 1.0)))
            opinions = new_opinions

        # Compute simulated distribution
        stances: dict[str, int] = {}
        for op in opinions:
            stance = _opinion_to_stance(op)
            stances[stance] = stances.get(stance, 0) + 1
        total = len(opinions)
        simulated = {k: v / total for k, v in stances.items()}

        return earth_movers_distance(simulated, target_distribution)

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="minimize", sampler=sampler)

    def objective(trial: optuna.Trial) -> float:
        ct = trial.suggest_float("confidence_threshold", 0.05, 1.0)
        st = trial.suggest_float("base_stubbornness", 0.1, 0.9)
        return _simulate_and_compute_emd(ct, st)

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_params = study.best_params
    best_emd = study.best_value
    return best_params, best_emd


def save_estimated_params(
    params: dict[str, Any],
    best_emd: float,
    path: Path | str,
    category: str | None = None,
) -> None:
    """Optuna 推定パラメータを YAML ファイルに保存する。

    Args:
        params: optimize_opinion_dynamics_params() が返す best_params 辞書。
        best_emd: 最良 EMD スコア。
        path: 保存先ファイルパス（親ディレクトリは自動生成）。
        category: テーマカテゴリ名（"economy", "security" 等）。省略可。
    """
    import yaml

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {
        "params": {k: float(v) for k, v in params.items()},
        "best_emd": float(best_emd),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    if category is not None:
        data["category"] = category

    with open(out, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=True)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class OpinionDynamicsEngine:
    """Bounded Confidence + Friedkin-Johnsen opinion dynamics on a weighted graph.

    Step 8 enhancements:
    - MAX_CONV_DELTA clamp on conversation update
    - FJ-MM memory anchor (compute_memory_anchor) replaces x_i(0)
    - Confirmation bias asymmetric weights (compute_confirmation_bias_weight)
    - Per-agent opinion history tracking (_per_agent_history)
    - Deterministic seed support
    """

    def __init__(
        self,
        agents: list[dict],
        edges: list[dict],
        confidence_threshold: float | np.ndarray = 0.3,
        edge_weight_decay: float = 0.0,
        seed: int | None = None,
    ) -> None:
        self.n = len(agents)
        self.agent_ids = [a["id"] for a in agents]
        self._id_to_idx = {a["id"]: i for i, a in enumerate(agents)}
        self._rng = np.random.default_rng(seed)

        # Store initial opinions (anchors for Friedkin-Johnsen)
        self._initial_opinions = np.array(
            [a["opinion_vector"] for a in agents], dtype=np.float64,
        )
        # Current opinions (mutated each step)
        self._opinions = self._initial_opinions.copy()
        self._dim = self._opinions.shape[1]

        # Stubbornness per agent
        self._stubbornness = np.array(
            [a.get("stubbornness", 0.5) for a in agents], dtype=np.float64,
        )

        # Per-agent or scalar confidence threshold
        if isinstance(confidence_threshold, np.ndarray):
            self._thresholds = confidence_threshold
        else:
            self._thresholds = np.full(self.n, confidence_threshold, dtype=np.float64)

        self._edge_weight_decay = edge_weight_decay
        self._timestep_count = 0

        # Build adjacency: for each agent, list of (neighbor_idx, weight)
        self._adj: list[list[tuple[int, float]]] = [[] for _ in range(self.n)]
        for e in edges:
            src = self._id_to_idx.get(e["agent_id"])
            tgt = self._id_to_idx.get(e["target_id"])
            if src is not None and tgt is not None:
                self._adj[src].append((tgt, e.get("strength", 1.0)))

        # History for convergence detection
        self._history: list[np.ndarray] = []

        # Per-agent opinion history for FJ-MM memory anchor (1D only)
        # Initialise with the agent's explicit history if provided, else just initial opinion
        self._per_agent_history: list[list[float]] = []
        for agent in agents:
            provided_history = agent.get("opinion_history")
            if provided_history:
                self._per_agent_history.append(list(provided_history))
            else:
                self._per_agent_history.append([agent["opinion_vector"][0]])

    # ----- propagation step ------------------------------------------------

    def propagation_step(self, timestep: int) -> PropagationStepResult:
        new_opinions = np.empty_like(self._opinions)
        max_delta = 0.0

        # Edge weight decay: reduce edge weights each timestep
        decay_factor = (1.0 - self._edge_weight_decay) ** self._timestep_count
        self._timestep_count += 1

        for i in range(self.n):
            s_i = self._stubbornness[i]
            x_i = self._opinions[i]

            # FJ-MM: use memory anchor instead of fixed x_i(0)
            # For multi-dimensional opinions we use the first dimension for memory anchor
            if self._dim == 1:
                memory_anchor_val = compute_memory_anchor(
                    self._per_agent_history[i],
                    initial_opinion=self._initial_opinions[i][0],
                )
                x_anchor = np.array([memory_anchor_val], dtype=np.float64)
            else:
                # Multi-dim: fall back to initial opinion
                x_anchor = self._initial_opinions[i].copy()

            # Collect qualifying neighbors with confirmation bias weighting
            weighted_sum = np.zeros(self._dim, dtype=np.float64)
            total_weight = 0.0

            for j, w in self._adj[i]:
                x_j = self._opinions[j]
                dist = np.linalg.norm(x_j - x_i)
                if dist <= self._thresholds[i]:
                    base_w = w * decay_factor
                    # Apply confirmation bias (1D only; multi-dim keeps base weight)
                    if self._dim == 1:
                        effective_w = compute_confirmation_bias_weight(
                            agent_opinion=float(x_i[0]),
                            neighbor_opinion=float(x_j[0]),
                            base_weight=base_w,
                        )
                    else:
                        effective_w = base_w
                    weighted_sum += effective_w * x_j
                    total_weight += effective_w

            if total_weight > 0.0:
                neighbor_mean = weighted_sum / total_weight
                unclamped_x = s_i * x_anchor + (1.0 - s_i) * neighbor_mean

                # MAX_CONV_DELTA clamp: limit the conversation-driven shift
                raw_delta = unclamped_x - x_i
                clamped_delta = np.clip(raw_delta, -MAX_CONV_DELTA, MAX_CONV_DELTA)
                new_x = x_i + clamped_delta
            else:
                # No qualifying neighbors: opinion unchanged
                new_x = x_i.copy()

            # Clip to [0, 1]
            new_x = np.clip(new_x, 0.0, 1.0)
            new_opinions[i] = new_x

            step_delta = float(np.linalg.norm(new_x - x_i))
            if step_delta > max_delta:
                max_delta = step_delta

        self._opinions = new_opinions

        # Update per-agent history (1D)
        if self._dim == 1:
            for i in range(self.n):
                self._per_agent_history[i].append(float(new_opinions[i][0]))

        self._history.append(new_opinions.copy())

        return PropagationStepResult(
            updated_opinions=new_opinions.tolist(),
            max_delta=float(max_delta),
            timestep=timestep,
        )

    # ----- convergence detection -------------------------------------------

    def detect_convergence(self, window: int = 3, epsilon: float = 0.01) -> bool:
        if len(self._history) < window:
            return False
        for k in range(1, window):
            diff = np.max(np.abs(self._history[-k] - self._history[-k - 1]))
            if diff > epsilon:
                return False
        return True

    def detect_variance_plateau(self, window: int = 3, tolerance: float = 0.01) -> bool:
        """意見分散が安定（plateau）したかを検出する。

        直近 window ステップで分散の変化率が tolerance 以内なら True。
        """
        if len(self._history) < window + 1:
            return False

        variances = [
            float(np.var(self._history[-(i + 1)]))
            for i in range(window + 1)
        ]
        # 最新 window ステップの分散変化が tolerance 以内か
        for i in range(window):
            if variances[0] == 0 and variances[i + 1] == 0:
                continue
            ref = max(variances[i + 1], 1e-10)
            if abs(variances[i] - variances[i + 1]) / ref > tolerance:
                return False
        return True

    # ----- cluster detection -----------------------------------------------

    def detect_clusters(self, eps: float = 0.2, min_samples: int = 2) -> list[ClusterInfo]:
        db = DBSCAN(eps=eps, min_samples=min_samples).fit(self._opinions)
        labels = db.labels_

        clusters: list[ClusterInfo] = []
        unique_labels = set(labels)
        unique_labels.discard(-1)  # noise

        for label in sorted(unique_labels):
            mask = labels == label
            indices = np.where(mask)[0]
            member_ids = [self.agent_ids[i] for i in indices]
            centroid = self._opinions[mask].mean(axis=0).tolist()
            clusters.append(ClusterInfo(
                label=int(label),
                member_ids=member_ids,
                centroid=centroid,
                size=len(member_ids),
            ))

        # Assign noise points as singleton clusters if any
        noise_indices = np.where(labels == -1)[0]
        next_label = max(unique_labels, default=-1) + 1
        for idx in noise_indices:
            clusters.append(ClusterInfo(
                label=next_label,
                member_ids=[self.agent_ids[idx]],
                centroid=self._opinions[idx].tolist(),
                size=1,
            ))
            next_label += 1

        return clusters
