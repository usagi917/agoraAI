"""社会グラフ進化テスト"""

import pytest
from sqlalchemy import select

from src.app.models.agent_profile import AgentProfile
from src.app.models.population import Population
from src.app.models.social_edge import SocialEdge
from src.app.services.society.graph_evolution import (
    _compute_interaction_strength,
    _graph_participants,
    evolve_social_graph,
)


class TestComputeInteractionStrength:
    def test_co_occurrence(self):
        rounds = [
            [
                {"participant_index": 0, "position": "賛成"},
                {"participant_index": 1, "position": "反対"},
            ],
            [
                {"participant_index": 0, "position": "条件付き賛成"},
                {"participant_index": 1, "position": "条件付き賛成"},
            ],
        ]
        delta = _compute_interaction_strength(rounds, "a", "b", 0, 1)
        assert delta > 0
        # 2/2 co-occurrence + 1/2 agreement
        assert delta <= 0.15

    def test_no_co_occurrence(self):
        rounds = [
            [{"participant_index": 0, "position": "賛成"}],
            [{"participant_index": 1, "position": "反対"}],
        ]
        delta = _compute_interaction_strength(rounds, "a", "b", 0, 1)
        assert delta == 0.0

    def test_empty_rounds(self):
        delta = _compute_interaction_strength([], "a", "b", 0, 1)
        assert delta == 0.0

    def test_full_agreement(self):
        rounds = [
            [
                {"participant_index": 0, "position": "賛成"},
                {"participant_index": 1, "position": "賛成"},
            ],
        ]
        delta = _compute_interaction_strength(rounds, "a", "b", 0, 1)
        assert delta > 0


class TestGraphParticipants:
    def test_skips_experts_and_keeps_citizens(self):
        participants = [
            {
                "participant_index": 0,
                "role": "citizen_representative",
                "agent_profile": {"id": "citizen-1"},
            },
            {
                "participant_index": 1,
                "role": "expert",
                "agent_profile": {"id": "expert-1"},
            },
            {
                "participant_index": 2,
                "role": "citizen_representative",
                "agent_profile": {"id": "citizen-2"},
            },
        ]

        assert _graph_participants(participants) == [
            (0, "citizen-1"),
            (2, "citizen-2"),
        ]


@pytest.mark.asyncio
async def test_evolve_social_graph_returns_before_after_for_existing_and_new_edges(db_session):
    db_session.add(Population(id="pop-evolution", agent_count=3, status="ready"))
    for index in range(3):
        db_session.add(AgentProfile(
            id=f"citizen-{index}",
            population_id="pop-evolution",
            agent_index=index,
            demographics={},
            big_five={},
        ))
    db_session.add(SocialEdge(
        id="existing-edge",
        population_id="pop-evolution",
        agent_id="citizen-0",
        target_id="citizen-1",
        relation_type="friend",
        strength=0.5,
    ))
    await db_session.commit()

    participants = [
        {
            "participant_index": index,
            "role": "citizen_representative",
            "agent_profile": {"id": f"citizen-{index}"},
        }
        for index in range(3)
    ]
    meeting_result = {
        "rounds": [[
            {"participant_index": index, "position": "賛成"}
            for index in range(3)
        ]]
    }

    result = await evolve_social_graph(
        db_session,
        "pop-evolution",
        meeting_result,
        participants,
    )

    assert result.updated_count == 3
    existing_change = next(change for change in result.changes if change.edge_id == "existing-edge")
    assert existing_change.before_strength == pytest.approx(0.5)
    assert existing_change.after_strength == pytest.approx(0.65)
    assert existing_change.delta == pytest.approx(0.15)
    assert existing_change.is_new is False

    new_changes = [change for change in result.changes if change.is_new]
    assert len(new_changes) == 2
    assert all(change.before_strength == 0 for change in new_changes)
    assert all(change.after_strength == pytest.approx(0.45) for change in new_changes)


@pytest.mark.asyncio
async def test_evolve_social_graph_updates_existing_edge_in_reverse_storage_order(db_session):
    db_session.add(Population(id="pop-reverse-edge", agent_count=2, status="ready"))
    db_session.add_all([
        AgentProfile(
            id="zzz-agent",
            population_id="pop-reverse-edge",
            agent_index=0,
            demographics={},
            big_five={},
        ),
        AgentProfile(
            id="aaa-agent",
            population_id="pop-reverse-edge",
            agent_index=1,
            demographics={},
            big_five={},
        ),
    ])
    db_session.add(SocialEdge(
        id="reverse-existing-edge",
        population_id="pop-reverse-edge",
        agent_id="zzz-agent",
        target_id="aaa-agent",
        relation_type="friend",
        strength=0.4,
    ))
    await db_session.commit()

    result = await evolve_social_graph(
        db_session,
        "pop-reverse-edge",
        {"rounds": [[
            {"participant_index": 0, "position": "賛成"},
            {"participant_index": 1, "position": "賛成"},
        ]]},
        [
            {
                "participant_index": 0,
                "role": "citizen_representative",
                "agent_profile": {"id": "zzz-agent"},
            },
            {
                "participant_index": 1,
                "role": "citizen_representative",
                "agent_profile": {"id": "aaa-agent"},
            },
        ],
    )

    assert result.updated_count == 1
    change = result.changes[0]
    assert change.edge_id == "reverse-existing-edge"
    assert change.is_new is False
    assert change.before_strength == pytest.approx(0.4)
    await db_session.commit()
    edges = (await db_session.execute(
        select(SocialEdge).where(
            SocialEdge.population_id == "pop-reverse-edge"
        )
    )).scalars().all()
    assert len(edges) == 1
