"""Audit Trail Service のテスト (Stream D)"""

import pytest

from src.app.services.audit_trail_service import (
    record_event,
    get_audit_trail,
    get_opinion_shifts,
    detect_opinion_shift,
)


class TestRecordEvent:
    @pytest.mark.asyncio
    async def test_record_event(self, db_session):
        from src.app.models.simulation import Simulation

        sim = Simulation(
            mode="standard", prompt_text="test", template_name="general",
            execution_profile="standard",
        )
        db_session.add(sim)
        await db_session.commit()

        event = await record_event(
            session=db_session,
            simulation_id=sim.id,
            agent_id="agent-001",
            agent_name="Alice",
            round_number=1,
            event_type="belief_change",
            before_state={"stance": 0.3},
            after_state={"stance": 0.7},
            reasoning="New evidence changed my view",
        )
        await db_session.commit()

        from src.app.models.audit_event import AuditEvent
        fetched = await db_session.get(AuditEvent, event.id)
        assert fetched is not None
        assert fetched.simulation_id == sim.id
        assert fetched.agent_id == "agent-001"
        assert fetched.agent_name == "Alice"
        assert fetched.round_number == 1
        assert fetched.event_type == "belief_change"
        assert fetched.before_state == {"stance": 0.3}
        assert fetched.after_state == {"stance": 0.7}
        assert fetched.reasoning == "New evidence changed my view"
        assert fetched.created_at is not None


class TestGetAuditTrail:
    @pytest.mark.asyncio
    async def test_get_audit_trail_all(self, db_session):
        from src.app.models.simulation import Simulation

        sim = Simulation(
            mode="standard", prompt_text="test", template_name="general",
            execution_profile="standard",
        )
        db_session.add(sim)
        await db_session.commit()

        for i in range(3):
            await record_event(
                session=db_session,
                simulation_id=sim.id,
                agent_id=f"agent-{i}",
                agent_name=f"Agent {i}",
                round_number=i,
                event_type="action",
                before_state={"v": i},
                after_state={"v": i + 1},
                reasoning=f"Reason {i}",
            )
        await db_session.commit()

        events = await get_audit_trail(db_session, sim.id)
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_get_audit_trail_by_agent(self, db_session):
        from src.app.models.simulation import Simulation

        sim = Simulation(
            mode="standard", prompt_text="test", template_name="general",
            execution_profile="standard",
        )
        db_session.add(sim)
        await db_session.commit()

        for agent_id in ["agent-A", "agent-B", "agent-A"]:
            await record_event(
                session=db_session,
                simulation_id=sim.id,
                agent_id=agent_id,
                agent_name=agent_id,
                round_number=1,
                event_type="action",
                before_state={},
                after_state={},
                reasoning="test",
            )
        await db_session.commit()

        events = await get_audit_trail(db_session, sim.id, agent_id="agent-A")
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_get_audit_trail_by_event_type(self, db_session):
        from src.app.models.simulation import Simulation

        sim = Simulation(
            mode="standard", prompt_text="test", template_name="general",
            execution_profile="standard",
        )
        db_session.add(sim)
        await db_session.commit()

        types = ["belief_change", "opinion_shift", "action", "opinion_shift"]
        for i, etype in enumerate(types):
            await record_event(
                session=db_session,
                simulation_id=sim.id,
                agent_id=f"agent-{i}",
                agent_name=f"Agent {i}",
                round_number=1,
                event_type=etype,
                before_state={},
                after_state={},
                reasoning="test",
            )
        await db_session.commit()

        events = await get_audit_trail(db_session, sim.id, event_type="opinion_shift")
        assert len(events) == 2


class TestGetOpinionShifts:
    @pytest.mark.asyncio
    async def test_get_opinion_shifts(self, db_session):
        from src.app.models.simulation import Simulation

        sim = Simulation(
            mode="standard", prompt_text="test", template_name="general",
            execution_profile="standard",
        )
        db_session.add(sim)
        await db_session.commit()

        types = ["belief_change", "opinion_shift", "action", "opinion_shift", "belief_change"]
        for i, etype in enumerate(types):
            await record_event(
                session=db_session,
                simulation_id=sim.id,
                agent_id=f"agent-{i}",
                agent_name=f"Agent {i}",
                round_number=1,
                event_type=etype,
                before_state={},
                after_state={},
                reasoning="test",
            )
        await db_session.commit()

        shifts = await get_opinion_shifts(db_session, sim.id)
        assert len(shifts) == 2
        assert all(e.event_type == "opinion_shift" for e in shifts)


class TestDetectOpinionShift:
    def test_detect_opinion_shift_changed(self):
        before = {"stance": 0.3, "confidence": 0.8}
        after = {"stance": 0.7, "confidence": 0.8}
        assert detect_opinion_shift(before, after) is True

    def test_detect_opinion_shift_unchanged(self):
        before = {"stance": 0.5, "confidence": 0.8}
        after = {"stance": 0.5, "confidence": 0.8}
        assert detect_opinion_shift(before, after) is False

    def test_detect_opinion_shift_empty_both(self):
        assert detect_opinion_shift({}, {}) is False

    def test_detect_opinion_shift_empty_before(self):
        assert detect_opinion_shift({}, {"stance": 0.5}) is True

    def test_detect_opinion_shift_new_key(self):
        before = {"stance": 0.5}
        after = {"stance": 0.5, "new_belief": 0.9}
        assert detect_opinion_shift(before, after) is True
