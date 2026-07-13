"""Deterministic paired sampling for GPT calibration calls."""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict


def _age_bucket(age: object) -> str:
    try:
        value = int(age)
    except (TypeError, ValueError):
        return "unknown"
    if value < 30:
        return "18-29"
    if value < 50:
        return "30-49"
    if value < 70:
        return "50-69"
    return "70+"


def _stable_seed(seed: int, key: tuple[str, ...]) -> int:
    digest = hashlib.sha256(f"{seed}|{'|'.join(key)}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def select_shadow_pairs(
    agents: list[dict],
    responses: list[dict],
    *,
    sample_size: int,
    seed: int | None,
) -> list[tuple[dict, dict]]:
    """Sample paired local outputs across stance and demographic strata."""
    pairs = [
        (agent, response)
        for agent, response in zip(agents, responses, strict=False)
        if not response.get("_failed")
    ]
    if sample_size <= 0 or not pairs:
        return []
    if sample_size >= len(pairs):
        return pairs

    resolved_seed = int(seed or 0)
    groups: dict[tuple[str, ...], list[tuple[dict, dict]]] = defaultdict(list)
    for agent, response in pairs:
        demographics = agent.get("demographics") or {}
        key = (
            str(response.get("stance") or "unknown"),
            str(demographics.get("region") or "unknown"),
            str(demographics.get("gender") or "unknown"),
            _age_bucket(demographics.get("age")),
        )
        groups[key].append((agent, response))

    for key, members in groups.items():
        random.Random(_stable_seed(resolved_seed, key)).shuffle(members)

    ordered_keys = sorted(groups)
    population_size = len(pairs)
    allocations = {
        key: sample_size * len(groups[key]) // population_size
        for key in ordered_keys
    }
    remaining = sample_size - sum(allocations.values())
    largest_remainders = sorted(
        ordered_keys,
        key=lambda key: (
            -(sample_size * len(groups[key]) % population_size),
            key,
        ),
    )
    for key in largest_remainders:
        if remaining <= 0:
            break
        if allocations[key] < len(groups[key]):
            allocations[key] += 1
            remaining -= 1

    selected: list[tuple[dict, dict]] = []
    for key in ordered_keys:
        selected.extend(groups[key][: allocations[key]])
    return selected
