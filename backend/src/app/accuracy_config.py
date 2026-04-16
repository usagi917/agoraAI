"""Accuracy configuration: feature flags for simulation accuracy improvements.

Each entry in KNOWN_FEATURES documents when a feature was added and what it does.
New entries should only be appended -- never modify or remove existing entries.
"""

KNOWN_FEATURES: dict[str, str] = {
    "agreeableness_in_dynamics": (
        "Agreeableness (A) from Big Five influences confidence thresholds and stubbornness. "
        "Higher A widens thresholds (more receptive) and slightly reduces stubbornness."
    ),
    "hybrid_network": (
        "Barabasi-Albert preferential attachment and hybrid (WS+BA) network topologies. "
        "BA provides scale-free hubs; hybrid combines WS clustering with BA hubs."
    ),
}
