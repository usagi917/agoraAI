"""個人特性ベース bounded confidence の人口伝播配線テスト。"""

import numpy as np
import pytest

from src.app.services.society import population_propagation
from src.app.services.society.opinion_dynamics import OpinionDynamicsEngine


def _agents() -> list[dict]:
    return [
        {"id": "low-c", "agent_index": 0, "big_five": {"C": 0.1, "O": 0.5, "A": 0.2}, "information_source": "新聞"},
        {"id": "high-c", "agent_index": 1, "big_five": {"C": 0.9, "O": 0.5, "A": 0.2}, "information_source": "新聞"},
        {"id": "high-a", "agent_index": 2, "big_five": {"C": 0.1, "O": 0.5, "A": 0.9}, "information_source": "新聞"},
    ]


def _capture_engine_threshold(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    captured: list[object] = []

    def spy_engine(*args, **kwargs):
        captured.append(kwargs["confidence_threshold"])
        return OpinionDynamicsEngine(*args, **kwargs)

    monkeypatch.setattr(population_propagation, "OpinionDynamicsEngine", spy_engine)
    return captured


@pytest.mark.asyncio
async def test_flag_off_passes_original_scalar_threshold(monkeypatch):
    monkeypatch.setattr(population_propagation, "is_enabled", lambda _feature: False)
    captured = _capture_engine_threshold(monkeypatch)
    await population_propagation.run_population_propagation(
        _agents(), [], [], confidence_threshold=0.37, seed=42,
    )
    assert captured == [0.37]
    assert isinstance(captured[0], float)
    assert not isinstance(captured[0], np.ndarray)


@pytest.mark.asyncio
async def test_flag_on_passes_non_uniform_per_agent_ndarray(monkeypatch):
    monkeypatch.setattr(population_propagation, "is_enabled", lambda _feature: True)
    captured = _capture_engine_threshold(monkeypatch)
    agents = _agents()
    await population_propagation.run_population_propagation(
        agents, [], [], confidence_threshold=0.37, seed=42,
    )
    threshold = captured[0]
    assert isinstance(threshold, np.ndarray)
    assert threshold.dtype == np.float64
    assert threshold.size == len(agents)
    assert np.unique(threshold).size > 1


@pytest.mark.asyncio
async def test_trait_based_propagation_is_deterministic_for_same_seed(monkeypatch):
    monkeypatch.setattr(population_propagation, "is_enabled", lambda _feature: True)
    agents = _agents()
    responses = [
        {"agent_id": "low-c", "stance": "賛成", "confidence": 0.8},
        {"agent_id": "high-c", "stance": "反対", "confidence": 0.7},
    ]
    edges = [
        {"agent_id": "low-c", "target_id": "high-c", "strength": 0.8},
        {"agent_id": "high-c", "target_id": "high-a", "strength": 0.6},
    ]
    first = await population_propagation.run_population_propagation(
        agents, responses, edges, seed=123, max_timesteps=6,
    )
    second = await population_propagation.run_population_propagation(
        agents, responses, edges, seed=123, max_timesteps=6,
    )
    assert first.final_stances == second.final_stances


@pytest.mark.asyncio
async def test_trait_directions_reach_population_engine(monkeypatch):
    monkeypatch.setattr(population_propagation, "is_enabled", lambda _feature: True)
    captured = _capture_engine_threshold(monkeypatch)
    await population_propagation.run_population_propagation(
        _agents(), [], [], confidence_threshold=0.5, seed=42,
    )
    threshold = captured[0]
    assert isinstance(threshold, np.ndarray)
    assert threshold[1] < threshold[0]  # 高 C はより狭い
    assert threshold[2] > threshold[0]  # 高 A はより広い
