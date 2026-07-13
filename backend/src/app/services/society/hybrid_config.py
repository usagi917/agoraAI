"""Validated runtime configuration for Liquid + GPT society activation."""

from __future__ import annotations

from dataclasses import dataclass

from src.app.config import settings


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _positive_float(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class BudgetConfig:
    hard_limit_usd: float = 0.85
    reserve_usd: float = 0.15
    shadow_stop_usd: float = 0.70

    @property
    def total_envelope_usd(self) -> float:
        return self.hard_limit_usd + self.reserve_usd


@dataclass(frozen=True)
class ActivationRoleConfig:
    provider: str
    max_tokens: int
    max_concurrency: int = 1
    chunk_size: int = 25
    target_count: int = 0
    sample_size: int = 0
    max_calls: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    minimal_output: bool = False


@dataclass(frozen=True)
class HybridInferenceConfig:
    enabled: bool
    budget: BudgetConfig
    population_activation: ActivationRoleConfig
    gpt_shadow: ActivationRoleConfig
    gpt_escalation: ActivationRoleConfig
    narrative_count: int = 100
    social_requery_max: int = 1_000


def _role_config(raw: dict, defaults: dict) -> ActivationRoleConfig:
    return ActivationRoleConfig(
        provider=str(raw.get("provider") or defaults["provider"]),
        max_tokens=_positive_int(raw.get("max_tokens"), defaults["max_tokens"]),
        max_concurrency=_positive_int(
            raw.get("max_concurrency"), defaults.get("max_concurrency", 1)
        ),
        chunk_size=_positive_int(raw.get("chunk_size"), defaults.get("chunk_size", 25)),
        target_count=max(0, int(raw.get("target_count") or defaults.get("target_count", 0))),
        sample_size=max(0, int(raw.get("sample_size") or defaults.get("sample_size", 0))),
        max_calls=max(0, int(raw.get("max_calls") or defaults.get("max_calls", 0))),
        estimated_input_tokens=max(
            0,
            int(raw.get("estimated_input_tokens") or defaults.get("estimated_input_tokens", 0)),
        ),
        estimated_output_tokens=max(
            0,
            int(raw.get("estimated_output_tokens") or defaults.get("estimated_output_tokens", 0)),
        ),
        minimal_output=bool(raw.get("minimal_output", defaults.get("minimal_output", False))),
    )


def load_hybrid_inference_config(raw: dict | None = None) -> HybridInferenceConfig:
    data = raw if raw is not None else settings.load_hybrid_inference_config()
    budget_raw = data.get("budget") or {}
    hard_limit = _positive_float(budget_raw.get("hard_limit_usd"), 0.85)
    reserve = _positive_float(budget_raw.get("reserve_usd"), 0.15)
    shadow_stop = _positive_float(budget_raw.get("shadow_stop_usd"), 0.70)
    shadow_stop = min(shadow_stop, hard_limit)

    return HybridInferenceConfig(
        enabled=bool(data.get("enabled", True)),
        budget=BudgetConfig(hard_limit, reserve, shadow_stop),
        population_activation=_role_config(
            data.get("population_activation") or {},
            {
                "provider": "liquid",
                "max_tokens": 160,
                "max_concurrency": 1,
                "chunk_size": 128,
                "target_count": 10_000,
                "minimal_output": True,
            },
        ),
        gpt_shadow=_role_config(
            data.get("gpt_shadow") or {},
            {
                "provider": "openai_shadow",
                "max_tokens": 120,
                "max_concurrency": 10,
                "chunk_size": 25,
                "sample_size": 800,
                "max_calls": 1_000,
                "estimated_input_tokens": 1_600,
                "estimated_output_tokens": 384,
            },
        ),
        gpt_escalation=_role_config(
            data.get("gpt_escalation") or {},
            {
                "provider": "openai_escalation",
                "max_tokens": 250,
                "max_concurrency": 5,
                "chunk_size": 10,
                "max_calls": 40,
                "estimated_input_tokens": 1_800,
                "estimated_output_tokens": 512,
            },
        ),
        narrative_count=_positive_int(data.get("narrative_count"), 100),
        social_requery_max=_positive_int(data.get("social_requery_max"), 1_000),
    )
