"""Per-run cost accounting and hard stops for hybrid inference."""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExceededError(RuntimeError):
    """Raised before a request that would exceed its allowed budget."""


@dataclass
class HybridBudgetGuard:
    hard_limit_usd: float = 0.85
    reserve_usd: float = 0.15
    shadow_stop_usd: float = 0.70
    spent_by_role: dict[str, float] = field(default_factory=dict)
    reserved_by_role: dict[str, float] = field(default_factory=dict)

    @property
    def spent_usd(self) -> float:
        return sum(self.spent_by_role.values())

    @property
    def reserved_usd(self) -> float:
        return sum(self.reserved_by_role.values())

    @property
    def total_envelope_usd(self) -> float:
        return self.hard_limit_usd + self.reserve_usd

    def _limit_for_role(self, role: str) -> float:
        if role == "shadow":
            return min(self.shadow_stop_usd, self.hard_limit_usd)
        if role in {"synthesis", "retry"}:
            return self.total_envelope_usd
        return self.hard_limit_usd

    def can_schedule(self, role: str, estimated_cost_usd: float) -> bool:
        if estimated_cost_usd < 0:
            return False
        projected = self.spent_usd + self.reserved_usd + estimated_cost_usd
        return projected <= self._limit_for_role(role) + 1e-12

    def reserve(self, role: str, estimated_cost_usd: float) -> None:
        if not self.can_schedule(role, estimated_cost_usd):
            raise BudgetExceededError(
                f"{role} request would exceed run budget: "
                f"spent={self.spent_usd:.4f}, reserved={self.reserved_usd:.4f}, "
                f"estimate={estimated_cost_usd:.4f}"
            )
        self.reserved_by_role[role] = self.reserved_by_role.get(role, 0.0) + estimated_cost_usd

    def record_cost(
        self, role: str, actual_cost_usd: float, reserved_cost_usd: float = 0.0
    ) -> None:
        if reserved_cost_usd:
            remaining = self.reserved_by_role.get(role, 0.0) - reserved_cost_usd
            self.reserved_by_role[role] = max(0.0, remaining)
        self.spent_by_role[role] = self.spent_by_role.get(role, 0.0) + max(0.0, actual_cost_usd)


def estimate_token_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    input_per_million_usd: float,
    output_per_million_usd: float,
    cached_input_tokens: int = 0,
    cached_input_per_million_usd: float = 0.0,
    batch_discount: float = 1.0,
) -> float:
    uncached = max(0, input_tokens - cached_input_tokens)
    total = (
        uncached * input_per_million_usd
        + cached_input_tokens * cached_input_per_million_usd
        + output_tokens * output_per_million_usd
    ) / 1_000_000
    return total * batch_discount
