"""LLM 出力のバリデーション"""


def validate_world_build(data: dict) -> None:
    if not isinstance(data.get("entities"), list):
        raise ValueError("entities は配列である必要があります")
    if not isinstance(data.get("relations"), list):
        raise ValueError("relations は配列である必要があります")
    for e in data["entities"]:
        if "id" not in e or "label" not in e:
            raise ValueError(f"entity に id と label が必要です: {e}")


def validate_agents(data: dict) -> None:
    if not isinstance(data.get("agents"), list):
        raise ValueError("agents は配列である必要があります")
    for a in data["agents"]:
        if "id" not in a or "name" not in a:
            raise ValueError(f"agent に id と name が必要です: {a}")


def validate_round_result(data: dict) -> None:
    for key in ("agent_decisions", "entity_updates", "relation_updates", "events"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"{key} は配列である必要があります")


def validate_entities_extraction(data: dict) -> None:
    if not isinstance(data.get("entities"), list):
        raise ValueError("entities は配列である必要があります")
    for e in data["entities"]:
        if "name" not in e:
            raise ValueError(f"entity に name が必要です: {e}")


def validate_relations_extraction(data: dict) -> None:
    if not isinstance(data.get("relations"), list):
        raise ValueError("relations は配列である必要があります")


def validate_bdi_deliberation(data: dict) -> None:
    if "chosen_action" not in data:
        raise ValueError("chosen_action が必要です")
    if "reasoning_chain" not in data:
        raise ValueError("reasoning_chain が必要です")


def validate_action_resolution(data: dict) -> None:
    if not isinstance(data.get("resolved_actions"), list):
        raise ValueError("resolved_actions は配列である必要があります")


def validate_evaluation(data: dict) -> None:
    required = ["goal_completion", "relationship_maintenance", "information_management",
                 "social_norm_adherence", "behavioral_consistency", "causal_plausibility",
                 "emergent_complexity", "overall_score"]
    for key in required:
        if key not in data:
            raise ValueError(f"{key} が必要です")
