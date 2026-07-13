"""End-to-end Liquid population activation with bounded GPT calibration."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.services.society.activation_layer import run_activation
from src.app.services.society.activation_store import (
    load_completed_responses,
    persist_activation_chunk,
)
from src.app.services.society.hybrid_budget import HybridBudgetGuard, estimate_token_cost
from src.app.services.society.hybrid_calibration import (
    correct_distribution_with_shadow,
    select_escalation_pairs,
)
from src.app.services.society.hybrid_config import (
    ActivationRoleConfig,
    HybridInferenceConfig,
    load_hybrid_inference_config,
)
from src.app.services.society.hybrid_ensemble import load_learned_hybrid_shrinkage
from src.app.services.society.hybrid_sampling import select_shadow_pairs

logger = logging.getLogger(__name__)


def _provider_config(provider: str) -> dict:
    return settings.load_llm_providers_config().get("providers", {}).get(provider, {})


def _estimated_call_cost(provider: str, role: ActivationRoleConfig) -> float:
    provider_config = _provider_config(provider)
    return estimate_token_cost(
        input_tokens=role.estimated_input_tokens,
        output_tokens=role.estimated_output_tokens,
        input_per_million_usd=float(provider_config.get("cost_per_1k_input", 0.0)) * 1_000,
        output_per_million_usd=float(provider_config.get("cost_per_1k_output", 0.0)) * 1_000,
    )


def _actual_usage_cost(provider: str, usage: dict) -> float:
    provider_config = _provider_config(provider)
    return (
        int(usage.get("prompt_tokens", 0) or 0)
        * float(provider_config.get("cost_per_1k_input", 0.0))
        + int(usage.get("completion_tokens", 0) or 0)
        * float(provider_config.get("cost_per_1k_output", 0.0))
    ) / 1_000


def _affordable_count(
    guard: HybridBudgetGuard,
    *,
    role_name: str,
    requested: int,
    per_call_cost: float,
) -> int:
    if requested <= 0:
        return 0
    if per_call_cost <= 0:
        return requested
    low = 0
    high = requested
    while low < high:
        middle = (low + high + 1) // 2
        if guard.can_schedule(role_name, per_call_cost * middle):
            low = middle
        else:
            high = middle - 1
    return low


def _valid_count(responses: list[dict]) -> int:
    return sum(not response.get("_failed") for response in responses)


async def _run_checkpointed_stage(
    session: AsyncSession,
    *,
    simulation_id: str,
    population_id: str,
    stage: str,
    agents: list[dict],
    theme: str,
    seed: int | None,
    role: ActivationRoleConfig,
    on_progress: Any = None,
) -> dict:
    completed = await load_completed_responses(
        session,
        simulation_id=simulation_id,
        stage=stage,
        run_seed=seed,
        provider=role.provider,
    )

    async def checkpoint(records: list[dict], _completed: int, _total: int) -> None:
        for record in records:
            provider = str(record.get("provider") or role.provider)
            record["cost_usd"] = _actual_usage_cost(
                provider,
                dict(record.get("usage") or {}),
            )
        await persist_activation_chunk(
            session,
            simulation_id=simulation_id,
            population_id=population_id,
            stage=stage,
            run_seed=seed,
            records=records,
        )

    return await run_activation(
        agents,
        theme,
        temperature=0.3 if role.provider == "liquid" else 0.5,
        max_tokens=role.max_tokens,
        max_concurrency=role.max_concurrency,
        on_progress=on_progress,
        provider_override=role.provider,
        compact=True,
        minimal=role.minimal_output,
        chunk_size=role.chunk_size,
        resume_responses=completed,
        on_chunk=checkpoint,
        abort_on_full_chunk_failure=role.provider == "liquid",
        require_provider_ready=role.provider == "liquid",
        # Paid retries can multiply a bill without usable usage metadata from the
        # failed attempt. Keep retries on the free local path only.
        max_retries=2 if role.provider == "liquid" else 0,
    )


def _merge_usage(*stage_usage: tuple[str, dict]) -> dict:
    merged: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "by_stage": {},
    }
    for stage, usage in stage_usage:
        if not usage:
            continue
        merged["by_stage"][stage] = usage
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            merged[key] += int(usage.get(key, 0) or 0)
    return merged


async def run_hybrid_social_requery(
    session: AsyncSession,
    *,
    simulation_id: str,
    population_id: str,
    agents: list[dict],
    initial_responses: list[dict],
    final_stances: list[dict],
    theme: str,
    seed: int | None,
    config: HybridInferenceConfig | None = None,
) -> dict:
    """数値的な社会更新で立場が変化した住民だけを Liquid で再推論する。"""
    resolved = config or load_hybrid_inference_config()
    final_by_id = {
        str(item.get("agent_id") or ""): str(item.get("stance") or "中立") for item in final_stances
    }
    response_by_id = {
        str(response.get("agent_id") or ""): response for response in initial_responses
    }
    changed_agents: list[dict] = []
    for agent in agents:
        agent_id = str(agent.get("id") or "")
        initial = response_by_id.get(agent_id)
        final_stance = final_by_id.get(agent_id)
        if (
            not initial
            or initial.get("_failed")
            or not final_stance
            or final_stance == initial.get("stance")
        ):
            continue
        social_agent = dict(agent)
        social_agent["social_context"] = {
            "initial_stance": str(initial.get("stance") or "中立"),
            "network_stance": final_stance,
        }
        changed_agents.append(social_agent)

    changed_strata = [
        {
            "agent_id": agent["id"],
            "stance": final_by_id.get(str(agent.get("id") or ""), "中立"),
            "confidence": float(
                response_by_id.get(str(agent.get("id") or ""), {}).get("confidence", 0.5)
                or 0.5
            ),
        }
        for agent in changed_agents
    ]
    selected_agents = [
        agent
        for agent, _ in select_shadow_pairs(
            changed_agents,
            changed_strata,
            sample_size=min(resolved.social_requery_max, len(changed_agents)),
            seed=seed,
        )
    ]
    if not selected_agents:
        return {
            "responses": [],
            "usage": {},
            "requeried_count": 0,
            "changed_count": len(changed_agents),
        }

    result = await _run_checkpointed_stage(
        session,
        simulation_id=simulation_id,
        population_id=population_id,
        stage="local_social",
        agents=selected_agents,
        theme=theme,
        seed=seed,
        role=resolved.population_activation,
    )
    return {
        **result,
        "requeried_count": _valid_count(result.get("responses", [])),
        "changed_count": len(changed_agents),
    }


async def run_hybrid_activation(
    session: AsyncSession,
    *,
    simulation_id: str,
    population_id: str,
    agents: list[dict],
    theme: str,
    seed: int | None,
    config: HybridInferenceConfig | None = None,
    on_progress: Any = None,
    theme_category: str = "unknown",
) -> dict:
    """Activate every resident locally and use GPT only for bounded paired checks."""
    resolved = config or load_hybrid_inference_config()
    guard = HybridBudgetGuard(
        hard_limit_usd=resolved.budget.hard_limit_usd,
        reserve_usd=resolved.budget.reserve_usd,
        shadow_stop_usd=resolved.budget.shadow_stop_usd,
    )

    local_result = await _run_checkpointed_stage(
        session,
        simulation_id=simulation_id,
        population_id=population_id,
        stage="local_initial",
        agents=agents,
        theme=theme,
        seed=seed,
        role=resolved.population_activation,
        on_progress=on_progress,
    )
    local_responses = local_result["responses"]
    aggregation = dict(local_result["aggregation"])
    activated_count = _valid_count(local_responses)
    aggregation.update(
        {
            "activated_count": activated_count,
            "gpt_validated_count": 0,
            "gpt_escalated_count": 0,
            "api_cost_usd": 0.0,
        }
    )
    if activated_count == 0:
        aggregation.update(
            {
                "hybrid_status": "local_activation_failed",
                "hybrid_calibration": {
                    "method": "paired_model_residual",
                    "paired_count": 0,
                    "is_ground_truth": False,
                    "applied": False,
                },
            }
        )
        return {**local_result, "aggregation": aggregation}

    requested_shadow = min(
        resolved.gpt_shadow.sample_size,
        resolved.gpt_shadow.max_calls or resolved.gpt_shadow.sample_size,
        activated_count,
    )
    shadow_per_call = _estimated_call_cost(resolved.gpt_shadow.provider, resolved.gpt_shadow)
    shadow_count = _affordable_count(
        guard,
        role_name="shadow",
        requested=requested_shadow,
        per_call_cost=shadow_per_call,
    )
    shadow_pairs = select_shadow_pairs(
        agents,
        local_responses,
        sample_size=shadow_count,
        seed=seed,
    )
    if not shadow_pairs:
        aggregation.update(
            {
                "hybrid_status": "local_only",
                "hybrid_calibration": {
                    "method": "paired_model_residual",
                    "paired_count": 0,
                    "is_ground_truth": False,
                    "applied": False,
                },
            }
        )
        return {**local_result, "aggregation": aggregation}

    shadow_agents = [agent for agent, _ in shadow_pairs]
    local_sample = [response for _, response in shadow_pairs]
    shadow_reservation = shadow_per_call * len(shadow_agents)
    guard.reserve("shadow", shadow_reservation)
    shadow_result = await _run_checkpointed_stage(
        session,
        simulation_id=simulation_id,
        population_id=population_id,
        stage="gpt_shadow",
        agents=shadow_agents,
        theme=theme,
        seed=seed,
        role=resolved.gpt_shadow,
    )
    shadow_cost = _actual_usage_cost(resolved.gpt_shadow.provider, shadow_result["usage"])
    guard.record_cost("shadow", shadow_cost, shadow_reservation)
    shadow_responses = shadow_result["responses"]
    if _valid_count(shadow_responses) == 0:
        aggregation.update(
            {
                "hybrid_status": "local_only_gpt_unavailable",
                "hybrid_calibration": {
                    "method": "paired_model_residual",
                    "paired_count": 0,
                    "is_ground_truth": False,
                    "applied": False,
                },
                "gpt_validated_count": 0,
                "api_cost_usd": round(guard.spent_usd, 6),
                "api_budget_limit_usd": resolved.budget.hard_limit_usd,
            }
        )
        return {
            **local_result,
            "aggregation": aggregation,
            "shadow_responses": shadow_responses,
            "escalation_responses": [],
            "usage": _merge_usage(
                ("local_initial", local_result.get("usage", {})),
                ("gpt_shadow", shadow_result.get("usage", {})),
            ),
        }

    escalation_candidates = select_escalation_pairs(
        local_sample,
        shadow_responses,
        max_calls=resolved.gpt_escalation.max_calls,
    )
    escalation_per_call = _estimated_call_cost(
        resolved.gpt_escalation.provider, resolved.gpt_escalation
    )
    escalation_count = _affordable_count(
        guard,
        role_name="escalation",
        requested=len(escalation_candidates),
        per_call_cost=escalation_per_call,
    )
    escalation_ids = [
        str(local.get("agent_id") or "") for local, _ in escalation_candidates[:escalation_count]
    ]
    agents_by_id = {str(agent.get("id") or ""): agent for agent in shadow_agents}
    escalation_agents = [
        agents_by_id[agent_id] for agent_id in escalation_ids if agent_id in agents_by_id
    ]
    escalation_result: dict = {"responses": [], "usage": {}}
    if escalation_agents:
        escalation_reservation = escalation_per_call * len(escalation_agents)
        guard.reserve("escalation", escalation_reservation)
        escalation_result = await _run_checkpointed_stage(
            session,
            simulation_id=simulation_id,
            population_id=population_id,
            stage="gpt_escalation",
            agents=escalation_agents,
            theme=theme,
            seed=seed,
            role=resolved.gpt_escalation,
        )
        escalation_cost = _actual_usage_cost(
            resolved.gpt_escalation.provider, escalation_result["usage"]
        )
        guard.record_cost("escalation", escalation_cost, escalation_reservation)

    escalated_by_id = {
        str(response.get("agent_id") or ""): response
        for response in escalation_result.get("responses", [])
        if not response.get("_failed")
    }
    effective_shadow = [
        escalated_by_id.get(str(response.get("agent_id") or ""), response)
        for response in shadow_responses
    ]
    learned_shrinkage = await load_learned_hybrid_shrinkage(
        session,
        theme_category=theme_category,
    )
    full_corrected_distribution, _ = correct_distribution_with_shadow(
        aggregation.get("stance_distribution", {}),
        local_sample,
        effective_shadow,
    )
    corrected_distribution, diagnostics = correct_distribution_with_shadow(
        aggregation.get("stance_distribution", {}),
        local_sample,
        effective_shadow,
        shrinkage=learned_shrinkage.shrinkage,
    )
    diagnostics.update(
        {
            "shrinkage": learned_shrinkage.shrinkage,
            "shrinkage_source": learned_shrinkage.source,
            "shrinkage_sample_count": learned_shrinkage.sample_count,
        }
    )
    aggregation.update(
        {
            "stance_distribution_liquid": dict(aggregation.get("stance_distribution", {})),
            "stance_distribution_hybrid_full": full_corrected_distribution,
            "stance_distribution": corrected_distribution,
            "hybrid_status": "calibrated",
            "hybrid_calibration": diagnostics,
            "gpt_validated_count": _valid_count(shadow_responses),
            "gpt_escalated_count": _valid_count(escalation_result.get("responses", [])),
            "api_cost_usd": round(guard.spent_usd, 6),
            "api_budget_limit_usd": resolved.budget.hard_limit_usd,
        }
    )

    return {
        **local_result,
        "aggregation": aggregation,
        "shadow_responses": shadow_responses,
        "escalation_responses": escalation_result.get("responses", []),
        "usage": _merge_usage(
            ("local_initial", local_result.get("usage", {})),
            ("gpt_shadow", shadow_result.get("usage", {})),
            ("gpt_escalation", escalation_result.get("usage", {})),
        ),
    }
