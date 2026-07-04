"""Phase 2: 時間経過に伴う人口の自然変化 (年齢 advance / 入退会)"""

from __future__ import annotations

import copy
import random
from collections.abc import Iterable
from typing import Any

DAYS_PER_YEAR = 365


def age_advance_cohort(
    agents: Iterable[dict[str, Any]],
    delta_days: int,
) -> list[dict[str, Any]]:
    """delta_days 経過後の年齢に進める. 端数は切捨."""
    years = delta_days // DAYS_PER_YEAR
    if years <= 0:
        return [copy.deepcopy(a) for a in agents]
    advanced: list[dict[str, Any]] = []
    for agent in agents:
        new_agent = copy.deepcopy(agent)
        new_agent["age"] = int(new_agent.get("age", 0)) + years
        advanced.append(new_agent)
    return advanced


def apply_birth_death(
    agents: Iterable[dict[str, Any]],
    delta_days: int,
    mortality_age: int = 85,
    birth_rate: float = 0.5,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """死亡 (mortality_age 超) を取り除き、birth_rate per year で新規参入を加える.

    Args:
        birth_rate: 1 年あたりの新規参入数 (整数化される; 端数は確率的に追加)
        seed: 決定論的乱数のためのシード
    """
    rng = random.Random(seed)
    years = delta_days / DAYS_PER_YEAR

    survivors = [
        copy.deepcopy(a)
        for a in agents
        if int(a.get("age", 0)) < mortality_age
    ]

    n_births_float = birth_rate * years
    n_births = int(n_births_float)
    fraction = n_births_float - n_births
    if rng.random() < fraction:
        n_births += 1

    next_id = max((a.get("agent_id", -1) for a in survivors), default=-1) + 1
    for offset in range(n_births):
        new_agent = {
            "agent_id": next_id + offset,
            "age": rng.randint(20, 40),
            "stance": "中立",
            "confidence": 0.5,
            "rolling_summary": "",
            "episodes": [],
        }
        survivors.append(new_agent)

    return survivors
