"""BDIReasoner: BDI状態の管理と更新"""

import logging

logger = logging.getLogger(__name__)


class BeliefBase:
    """信念ベース: {proposition, confidence, source, round} のリスト。"""

    def __init__(self):
        self._beliefs: list[dict] = []

    def add(self, proposition: str, confidence: float, source: str, round_number: int) -> None:
        # 既存の同一命題を更新
        for b in self._beliefs:
            if b["proposition"] == proposition:
                if confidence > b["confidence"]:
                    b["confidence"] = confidence
                    b["source"] = source
                    b["round"] = round_number
                return
        self._beliefs.append({
            "proposition": proposition,
            "confidence": confidence,
            "source": source,
            "round": round_number,
        })

    def update_from_observations(self, observations: list[dict], round_number: int, threshold: float = 0.3) -> None:
        """観察から信念を更新する。"""
        for obs in observations:
            relevance = obs.get("relevance", 0.5)
            if relevance >= threshold:
                self.add(obs["content"], relevance, obs.get("source", "observation"), round_number)

    def update_from_deliberation(self, belief_updates: list[dict], round_number: int) -> None:
        """熟慮結果から信念を更新する。"""
        for bu in belief_updates:
            self.add(
                bu["proposition"],
                bu.get("confidence", 0.5),
                bu.get("source", "inference"),
                round_number,
            )

    def bayesian_update(self, evidence: str, likelihood_ratio: float, round_number: int) -> None:
        """ベイズ的信念更新: 証拠に基づいて関連する信念の確信度を更新する。

        P(H|E) ∝ P(E|H) * P(H)
        likelihood_ratio = P(E|H) / P(E|¬H)
        """
        for belief in self._beliefs:
            # 証拠と信念の関連性を簡易チェック（キーワード一致）
            evidence_words = set(evidence.lower().split())
            belief_words = set(belief["proposition"].lower().split())
            overlap = len(evidence_words & belief_words)

            if overlap > 0:
                prior = belief["confidence"]
                # ベイズ更新
                posterior = (likelihood_ratio * prior) / (
                    likelihood_ratio * prior + (1 - prior)
                )
                posterior = max(0.01, min(0.99, posterior))

                if abs(posterior - prior) > 0.05:
                    belief["confidence"] = posterior
                    belief["source"] = "bayesian_update"
                    belief["round"] = round_number
                    logger.debug(
                        "Bayesian update: '%s' %.2f -> %.2f (evidence: %s)",
                        belief["proposition"][:30], prior, posterior, evidence[:30],
                    )

    def get_beliefs(self, min_confidence: float = 0.0) -> list[dict]:
        return [b for b in self._beliefs if b["confidence"] >= min_confidence]

    def to_list(self) -> list[dict]:
        return list(self._beliefs)


class Desire:
    """欲求: {goal_text, priority, conditions}。"""

    def __init__(self, goal_text: str, priority: float, conditions: list[str] | None = None):
        self.goal_text = goal_text
        self.priority = priority
        self.conditions = conditions or []

    def to_dict(self) -> dict:
        return {
            "goal_text": self.goal_text,
            "priority": self.priority,
            "conditions": self.conditions,
        }


class Intention:
    """意図: {plan_text, status, commitment_strength}。"""

    def __init__(self, plan_text: str, commitment_strength: float = 1.0):
        self.plan_text = plan_text
        self.status = "active"
        self.commitment_strength = commitment_strength

    def to_dict(self) -> dict:
        return {
            "plan_text": self.plan_text,
            "status": self.status,
            "commitment_strength": self.commitment_strength,
        }


class BDIReasoner:
    """BDI状態の管理と推論支援。"""

    def __init__(self, belief_update_threshold: float = 0.3):
        self.belief_update_threshold = belief_update_threshold

    def initialize_from_agent_profile(self, agent: dict) -> tuple[BeliefBase, list[Desire], list[Intention]]:
        """エージェントプロファイルからBDI初期状態を生成する。"""
        beliefs = BeliefBase()
        beliefs.add(
            f"自分は{agent.get('role', 'unknown')}である",
            1.0, "self", 0,
        )
        if agent.get("strategy"):
            beliefs.add(f"基本戦略: {agent['strategy']}", 0.9, "self", 0)

        desires = []
        for goal in agent.get("goals", []):
            desires.append(Desire(goal, priority=0.7))

        intentions = []
        if agent.get("decision_pattern"):
            intentions.append(Intention(agent["decision_pattern"], commitment_strength=0.8))

        return beliefs, desires, intentions
