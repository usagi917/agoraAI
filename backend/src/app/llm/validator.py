"""LLM 出力のバリデーション."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


def _ensure_dict(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} はオブジェクトである必要があります")
    return value


def _validate_probability(value: Any, *, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} は数値である必要があります") from exc
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{label} は 0.0 から 1.0 の範囲である必要があります")
    return numeric


class _StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class WorldEntityModel(_StrictBaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    entity_type: str = "unknown"
    importance_score: float = 0.5
    activity_score: float = 0.5
    sentiment_score: float = 0.0

    @field_validator("importance_score", "activity_score")
    @classmethod
    def _validate_unit_interval(cls, value: float) -> float:
        return _validate_probability(value, label="entity score")

    @field_validator("sentiment_score")
    @classmethod
    def _validate_sentiment(cls, value: float) -> float:
        numeric = float(value)
        if not -1.0 <= numeric <= 1.0:
            raise ValueError("sentiment_score は -1.0 から 1.0 の範囲である必要があります")
        return numeric


class WorldRelationModel(_StrictBaseModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relation_type: str = "unknown"
    weight: float = 0.5

    @field_validator("weight")
    @classmethod
    def _validate_weight(cls, value: float) -> float:
        return _validate_probability(value, label="relation weight")


class WorldBuildPayload(_StrictBaseModel):
    entities: list[WorldEntityModel]
    relations: list[WorldRelationModel]
    timeline: list[Any] = Field(default_factory=list)
    world_summary: str = ""

    @model_validator(mode="after")
    def _validate_links(self) -> "WorldBuildPayload":
        entity_ids = [entity.id for entity in self.entities]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("entity id は一意である必要があります")
        known_ids = set(entity_ids)
        for relation in self.relations:
            if relation.source not in known_ids:
                raise ValueError(f"relation.source が未知の entity を参照しています: {relation.source}")
            if relation.target not in known_ids:
                raise ValueError(f"relation.target が未知の entity を参照しています: {relation.target}")
        return self


class AgentPayloadModel(_StrictBaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    role: str | None = None
    source_entity_id: str | None = None
    goals: list[Any] = Field(default_factory=list)


class AgentsPayload(_StrictBaseModel):
    agents: list[AgentPayloadModel]

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> "AgentsPayload":
        agent_ids = [agent.id for agent in self.agents]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("agent id は一意である必要があります")
        return self


class EntityUpdateModel(_StrictBaseModel):
    entity_id: str = Field(min_length=1)
    changes: dict[str, Any] = Field(default_factory=dict)


class RelationUpdateModel(_StrictBaseModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    changes: dict[str, Any] = Field(default_factory=dict)


class TimelineEventModel(_StrictBaseModel):
    event_type: str = "unknown"
    title: str = ""
    description: str = ""
    severity: float = 0.5
    involved_entities: list[Any] = Field(default_factory=list)

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, value: float) -> float:
        return _validate_probability(value, label="event severity")


class RoundResultPayload(_StrictBaseModel):
    agent_decisions: list[Any]
    entity_updates: list[EntityUpdateModel]
    relation_updates: list[RelationUpdateModel]
    events: list[TimelineEventModel]


class ExtractedEntityModel(_StrictBaseModel):
    name: str = Field(min_length=1)


class ExtractedEntitiesPayload(_StrictBaseModel):
    entities: list[ExtractedEntityModel]


class ExtractedRelationsPayload(_StrictBaseModel):
    relations: list[dict[str, Any]]


class EvaluationPayload(_StrictBaseModel):
    goal_completion: float
    relationship_maintenance: float
    information_management: float
    social_norm_adherence: float
    behavioral_consistency: float
    causal_plausibility: float
    emergent_complexity: float
    overall_score: float

    @field_validator("*")
    @classmethod
    def _validate_scores(cls, value: float) -> float:
        return _validate_probability(value, label="evaluation score")


def _validate_with_model(model: type[BaseModel], data: dict[str, Any], *, label: str) -> None:
    payload = _ensure_dict(data, label=label)
    try:
        model.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def validate_world_build(data: dict) -> None:
    _validate_with_model(WorldBuildPayload, data, label="world_build")


def validate_agents(data: dict) -> None:
    _validate_with_model(AgentsPayload, data, label="agents")


def validate_round_result(data: dict) -> None:
    _validate_with_model(RoundResultPayload, data, label="round_result")


def validate_entities_extraction(data: dict) -> None:
    _validate_with_model(ExtractedEntitiesPayload, data, label="entities_extraction")


def validate_relations_extraction(data: dict) -> None:
    _validate_with_model(ExtractedRelationsPayload, data, label="relations_extraction")


def validate_bdi_deliberation(data: dict) -> None:
    payload = _ensure_dict(data, label="bdi_deliberation")
    if "chosen_action" not in payload:
        raise ValueError("chosen_action が必要です")
    if "reasoning_chain" not in payload:
        raise ValueError("reasoning_chain が必要です")


def validate_action_resolution(data: dict) -> None:
    payload = _ensure_dict(data, label="action_resolution")
    if not isinstance(payload.get("resolved_actions"), list):
        raise ValueError("resolved_actions は配列である必要があります")


def validate_evaluation(data: dict) -> None:
    _validate_with_model(EvaluationPayload, data, label="evaluation")


def validate_pm_board_output(data: dict) -> None:
    payload = _ensure_dict(data, label="pm_board")
    sections = _ensure_dict(payload.get("sections"), label="pm_board.sections")

    required_section_keys = {
        "core_question",
        "assumptions",
        "uncertainties",
        "risks",
        "winning_hypothesis",
        "customer_validation_plan",
        "market_view",
        "gtm_hypothesis",
        "mvp_scope",
        "plan_30_60_90",
        "top_5_actions",
    }
    missing = sorted(key for key in required_section_keys if key not in sections)
    if missing:
        raise ValueError(f"pm_board.sections に必要なキーが不足しています: {', '.join(missing)}")

    if not isinstance(sections.get("top_5_actions"), list):
        raise ValueError("pm_board.sections.top_5_actions は配列である必要があります")
    for action in sections.get("top_5_actions", []):
        item = _ensure_dict(action, label="pm_board.top_5_actions[]")
        if not str(item.get("action", "")).strip():
            raise ValueError("pm_board.top_5_actions[].action が必要です")

    confidence = payload.get("overall_confidence")
    if confidence is not None:
        _validate_probability(confidence, label="pm_board.overall_confidence")


TASK_VALIDATORS = {
    "world_build": validate_world_build,
    "agent_generate": validate_agents,
    "round_process": validate_round_result,
    "entity_extract": validate_entities_extraction,
    "relation_extract": validate_relations_extraction,
    "bdi_deliberate": validate_bdi_deliberation,
    "gm_action_resolve": validate_action_resolution,
}


def get_task_validator(task_name: str):
    return TASK_VALIDATORS.get(task_name)
