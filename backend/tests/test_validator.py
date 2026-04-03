import pytest
from pydantic import ValidationError

from src.app.llm.validator import (
    AgentPayloadModel,
    validate_agents,
    validate_pm_board_output,
    validate_round_result,
    validate_world_build,
)


def test_validate_world_build_rejects_unknown_relation_target():
    with pytest.raises(ValueError, match="未知の entity"):
        validate_world_build(
            {
                "entities": [{"id": "e1", "label": "Company"}],
                "relations": [{"source": "e1", "target": "missing", "relation_type": "competes_with"}],
            }
        )


def test_validate_agents_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="一意"):
        validate_agents(
            {
                "agents": [
                    {"id": "a1", "name": "Alice"},
                    {"id": "a1", "name": "Bob"},
                ]
            }
        )


def test_validate_round_result_rejects_out_of_range_event_severity():
    with pytest.raises(ValueError, match="0.0 から 1.0"):
        validate_round_result(
            {
                "agent_decisions": [],
                "entity_updates": [],
                "relation_updates": [],
                "events": [
                    {
                        "event_type": "risk",
                        "title": "Spike",
                        "description": "unexpected",
                        "severity": 1.5,
                        "involved_entities": [],
                    }
                ],
            }
        )


def test_validate_pm_board_output_requires_top_level_sections():
    with pytest.raises(ValueError, match="不足"):
        validate_pm_board_output(
            {
                "type": "pm_board",
                "sections": {
                    "core_question": "What is true?",
                    "assumptions": [],
                },
                "overall_confidence": 0.6,
            }
        )


# ---------------------------------------------------------------------------
# AgentPayloadModel: source_entity_id + name max_length (spec F/G)
# ---------------------------------------------------------------------------


def test_agent_source_entity_id_preserved():
    model = AgentPayloadModel.model_validate(
        {"id": "a1", "name": "Alice", "source_entity_id": "uuid-abc-123"}
    )
    assert model.source_entity_id == "uuid-abc-123"


def test_agent_source_entity_id_optional():
    model = AgentPayloadModel.model_validate({"id": "a1", "name": "Alice"})
    assert model.source_entity_id is None


def test_agent_name_max_length():
    with pytest.raises(ValidationError):
        AgentPayloadModel.model_validate({"id": "a1", "name": "x" * 201})
