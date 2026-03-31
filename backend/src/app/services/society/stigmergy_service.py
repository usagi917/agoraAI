"""Stigmergy Service: pheromone-based topic importance tracking.

Implements indirect coordination through a shared information board where
topic importance accumulates from agent mentions and decays over time.

Inspired by ant colony optimization pheromone mechanisms:
- deposit(): agents reinforce topics they mention
- evaporate(): importance decays each timestep
- get_salient_topics(): returns highest-importance topics

Reference: Dorigo (1992), Ant Colony Optimization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TopicTrace:
    topic: str
    intensity: float = 0.0
    contributors: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "intensity": self.intensity,
            "contributors": list(self.contributors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TopicTrace:
        return cls(
            topic=data["topic"],
            intensity=data["intensity"],
            contributors=set(data.get("contributors", [])),
        )


class StigmergyBoard:
    """Shared information space for topic importance tracking."""

    def __init__(self) -> None:
        self._topics: dict[str, TopicTrace] = {}

    def deposit(self, agent_id: str, topic: str, intensity: float = 1.0) -> None:
        """Agent deposits pheromone on a topic."""
        if topic not in self._topics:
            self._topics[topic] = TopicTrace(topic=topic)
        self._topics[topic].intensity += intensity
        self._topics[topic].contributors.add(agent_id)

    def evaporate(self, decay_rate: float = 0.1) -> None:
        """Decay all topic intensities by decay_rate fraction."""
        for trace in self._topics.values():
            trace.intensity *= (1 - decay_rate)

    def get_salient_topics(self, top_k: int = 5) -> list[TopicTrace]:
        """Return top-K topics ranked by intensity."""
        if not self._topics:
            return []
        sorted_topics = sorted(
            self._topics.values(),
            key=lambda t: t.intensity,
            reverse=True,
        )
        return sorted_topics[:top_k]

    def to_dict(self) -> dict[str, Any]:
        return {
            "topics": {k: v.to_dict() for k, v in self._topics.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StigmergyBoard:
        board = cls()
        for key, trace_data in data.get("topics", {}).items():
            board._topics[key] = TopicTrace.from_dict(trace_data)
        return board
