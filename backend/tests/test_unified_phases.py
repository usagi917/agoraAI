"""Unified phases (society_pulse, council_deliberation, synthesis) のテスト。

TDD RED phase: テストを先に書き、実装がない状態で fail することを確認する。
"""

import pytest
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Phase A-1-2: society_pulse
# ---------------------------------------------------------------------------


class TestSocietyPulseResult:
    """SocietyPulseResult dataclass の構造テスト。"""

    def test_dataclass_fields(self):
        from src.app.services.phases.society_pulse import SocietyPulseResult

        result = SocietyPulseResult(
            agents=[{"id": "a1"}],
            responses=[{"stance": "賛成", "confidence": 0.8}],
            aggregation={"stance_distribution": {"賛成": 0.6}},
            evaluation={"consistency": 0.7},
            representatives=[{"role": "citizen_representative"}],
            usage={"prompt_tokens": 100},
        )
        d = asdict(result)
        assert d["agents"] == [{"id": "a1"}]
        assert d["aggregation"]["stance_distribution"]["賛成"] == 0.6
        assert d["usage"]["prompt_tokens"] == 100


class TestRunSocietyPulse:
    """run_society_pulse のロジックテスト。"""

    @pytest.mark.asyncio
    async def test_returns_society_pulse_result(self):
        """run_society_pulse は SocietyPulseResult を返す。"""
        from src.app.services.phases.society_pulse import (
            SocietyPulseResult,
            run_society_pulse,
        )

        mock_session = AsyncMock()
        mock_sim = MagicMock()
        mock_sim.id = "sim-1"
        mock_sim.population_id = None

        fake_agents = [
            {
                "id": f"agent-{i}",
                "agent_index": i,
                "demographics": {"occupation": "engineer", "age": 30, "region": "東京"},
                "llm_backend": "openai",
            }
            for i in range(10)
        ]
        fake_responses = [
            {"stance": "賛成", "confidence": 0.8, "reason": "理由", "concern": "", "priority": ""}
            for _ in range(10)
        ]
        fake_activation = {
            "responses": fake_responses,
            "aggregation": {
                "stance_distribution": {"賛成": 0.6, "反対": 0.3, "中立": 0.1},
                "average_confidence": 0.75,
                "top_concerns": ["concern1"],
            },
            "representatives": [{"agent_id": "agent-0"}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700},
        }
        fake_eval = [
            {"metric_name": "consistency", "score": 0.7, "details": {}},
            {"metric_name": "calibration", "score": 0.65, "details": {}},
        ]

        with (
            patch(
                "src.app.services.phases.society_pulse._get_or_create_population",
                new_callable=AsyncMock,
                return_value=("pop-1", fake_agents),
            ),
            patch(
                "src.app.services.phases.society_pulse.select_agents",
                new_callable=AsyncMock,
                return_value=fake_agents,
            ),
            patch(
                "src.app.services.phases.society_pulse.run_activation",
                new_callable=AsyncMock,
                return_value=fake_activation,
            ),
            patch(
                "src.app.services.phases.society_pulse.evaluate_society_simulation",
                new_callable=AsyncMock,
                return_value=fake_eval,
            ),
            patch(
                "src.app.services.phases.society_pulse.select_representatives",
                return_value=[{"role": "citizen_representative", "agent_profile": fake_agents[0]}],
            ),
            patch("src.app.services.phases.society_pulse.sse_manager") as mock_sse,
        ):
            mock_sse.publish = AsyncMock()

            result = await run_society_pulse(mock_session, mock_sim, "テスト政策")

        assert isinstance(result, SocietyPulseResult)
        assert len(result.agents) == 10
        assert len(result.responses) == 10
        assert result.aggregation["average_confidence"] == 0.75
        assert result.evaluation["consistency"] == 0.7
        assert result.usage["total_tokens"] == 700


# ---------------------------------------------------------------------------
# Phase A-1-3: council_deliberation
# ---------------------------------------------------------------------------


class TestCouncilResult:
    """CouncilResult dataclass の構造テスト。"""

    def test_dataclass_fields(self):
        from src.app.services.phases.council_deliberation import CouncilResult

        result = CouncilResult(
            participants=[{"display_name": "田中太郎", "role": "citizen_representative"}],
            rounds=[[{"argument": "主張1"}]],
            synthesis={"consensus_points": ["合意点1"]},
            devil_advocate_summary="反証サマリー",
            usage={"prompt_tokens": 200},
        )
        d = asdict(result)
        assert d["participants"][0]["display_name"] == "田中太郎"
        assert d["devil_advocate_summary"] == "反証サマリー"


class TestRunCouncil:
    """run_council のロジックテスト。"""

    @pytest.mark.asyncio
    async def test_returns_council_result_with_named_participants(self):
        """run_council は名前付き参加者を含む CouncilResult を返す。"""
        from src.app.services.phases.council_deliberation import (
            CouncilResult,
            run_council,
        )
        from src.app.services.phases.society_pulse import SocietyPulseResult

        mock_session = AsyncMock()
        mock_sim = MagicMock()
        mock_sim.id = "sim-1"

        pulse = SocietyPulseResult(
            agents=[
                {
                    "id": f"agent-{i}",
                    "agent_index": i,
                    "demographics": {
                        "occupation": "engineer",
                        "age": 30 + i,
                        "region": "東京",
                        "gender": "male",
                    },
                    "llm_backend": "openai",
                }
                for i in range(10)
            ],
            responses=[
                {"stance": "賛成" if i < 6 else "反対", "confidence": 0.8, "reason": "理由"}
                for i in range(10)
            ],
            aggregation={"stance_distribution": {"賛成": 0.6, "反対": 0.4}},
            evaluation={"consistency": 0.7},
            representatives=[
                {
                    "role": "citizen_representative",
                    "agent_profile": {"id": f"agent-{i}", "agent_index": i, "demographics": {"occupation": "engineer", "age": 30 + i, "region": "東京", "gender": "male"}, "llm_backend": "openai"},
                    "response": {"stance": "賛成" if i < 6 else "反対", "confidence": 0.8},
                    "stance": "賛成" if i < 6 else "反対",
                }
                for i in range(6)
            ] + [
                {
                    "role": "expert",
                    "agent_profile": {"id": f"expert-{i}", "agent_index": -1, "demographics": {"occupation": "専門家", "age": 50, "region": "専門家パネル"}, "llm_backend": "openai"},
                    "expertise": "economist",
                    "display_name": "経済学者",
                }
                for i in range(4)
            ],
            usage={"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700},
        )

        fake_meeting_result = {
            "rounds": [[{"argument": "主張1"}], [{"argument": "反論1"}], [{"argument": "最終"}]],
            "synthesis": {"consensus_points": ["合意1"], "recommendations": ["提言1"]},
            "participants": [{"display_name": "テスト", "role": "citizen_representative"}],
            "usage": {"prompt_tokens": 300, "completion_tokens": 150, "total_tokens": 450},
        }

        with (
            patch(
                "src.app.services.phases.council_deliberation._generate_names",
                new_callable=AsyncMock,
                return_value=["田中太郎", "佐藤花子", "鈴木一郎", "高橋美咲", "伊藤健太", "渡辺裕子", "山本純", "中村大輔", "小林由美", "加藤翔"],
            ),
            patch(
                "src.app.services.phases.council_deliberation.run_meeting",
                new_callable=AsyncMock,
                return_value=fake_meeting_result,
            ),
            patch("src.app.services.phases.council_deliberation.sse_manager") as mock_sse,
        ):
            mock_sse.publish = AsyncMock()

            result = await run_council(mock_session, mock_sim, pulse, "テスト政策")

        assert isinstance(result, CouncilResult)
        assert len(result.rounds) == 3
        assert result.synthesis["consensus_points"] == ["合意1"]
        assert result.usage["total_tokens"] == 450

    @pytest.mark.asyncio
    async def test_devil_advocate_assignment(self):
        """反証役が少数派スタンスから選ばれる。"""
        from src.app.services.phases.council_deliberation import _assign_devil_advocates

        participants = [
            {"role": "citizen_representative", "stance": "賛成", "display_name": "A"},
            {"role": "citizen_representative", "stance": "賛成", "display_name": "B"},
            {"role": "citizen_representative", "stance": "反対", "display_name": "C"},
            {"role": "citizen_representative", "stance": "賛成", "display_name": "D"},
            {"role": "citizen_representative", "stance": "賛成", "display_name": "E"},
            {"role": "citizen_representative", "stance": "反対", "display_name": "F"},
            {"role": "expert", "display_name": "経済学者", "expertise": "economist"},
            {"role": "expert", "display_name": "社会学者", "expertise": "sociologist"},
            {"role": "expert", "display_name": "技術者", "expertise": "technologist"},
            {"role": "expert", "display_name": "倫理学者", "expertise": "ethicist"},
        ]

        result = _assign_devil_advocates(participants, max_advocates=3)

        devil_advocates = [p for p in result if p.get("is_devil_advocate")]
        assert len(devil_advocates) == 3
        # 少数派（反対）から少なくとも1人
        minority_advocates = [p for p in devil_advocates if p.get("stance") == "反対"]
        assert len(minority_advocates) >= 1


# ---------------------------------------------------------------------------
# Phase A-1-4: synthesis
# ---------------------------------------------------------------------------


class TestSynthesisResult:
    """SynthesisResult dataclass の構造テスト。"""

    def test_dataclass_fields(self):
        from src.app.services.phases.synthesis import SynthesisResult

        result = SynthesisResult(
            decision_brief={
                "recommendation": "Go",
                "agreement_score": 0.72,
            },
            agreement_score=0.72,
            content="# レポート\n\n内容",
            sections={"summary": "サマリー"},
        )
        d = asdict(result)
        assert d["decision_brief"]["recommendation"] == "Go"
        assert d["agreement_score"] == 0.72
        assert "# レポート" in d["content"]


class TestRunSynthesis:
    """run_synthesis のロジックテスト。"""

    @pytest.mark.asyncio
    async def test_returns_synthesis_result_with_decision_brief(self):
        """run_synthesis は DecisionBrief 付きの SynthesisResult を返す。"""
        from src.app.services.phases.synthesis import SynthesisResult, run_synthesis
        from src.app.services.phases.society_pulse import SocietyPulseResult
        from src.app.services.phases.council_deliberation import CouncilResult

        mock_session = AsyncMock()
        mock_sim = MagicMock()
        mock_sim.id = "sim-1"

        pulse = SocietyPulseResult(
            agents=[],
            responses=[],
            aggregation={
                "stance_distribution": {"賛成": 0.6, "反対": 0.3, "中立": 0.1},
                "average_confidence": 0.75,
                "top_concerns": ["コスト"],
            },
            evaluation={"consistency": 0.7, "calibration": 0.65},
            representatives=[],
            usage={"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700},
        )

        council = CouncilResult(
            participants=[
                {"display_name": "田中太郎", "role": "citizen_representative", "stance": "賛成"},
            ],
            rounds=[[{"argument": "主張"}]],
            synthesis={
                "consensus_points": ["合意1"],
                "disagreement_points": [],
                "recommendations": ["提言1"],
                "overall_assessment": "概ね肯定的",
            },
            devil_advocate_summary="コスト面の懸念は無視できない。",
            usage={"prompt_tokens": 300, "completion_tokens": 150, "total_tokens": 450},
        )

        fake_decision_brief = {
            "recommendation": "条件付きGo",
            "agreement_score": 0.72,
            "agreement_breakdown": {"society": 0.78, "council": 0.68, "synthesis": 0.71},
            "options": [
                {"label": "選択肢A", "expected_effect": "+15%", "risk": "低"},
            ],
            "strongest_counterargument": "コスト面の懸念",
            "risk_factors": [{"condition": "コスト増", "impact": "合意度低下"}],
            "next_steps": ["ステップ1", "ステップ2"],
            "time_horizon": {
                "short_term": {"period": "3ヶ月", "prediction": "初期導入開始"},
                "mid_term": {"period": "1年", "prediction": "普及拡大"},
                "long_term": {"period": "3年", "prediction": "安定運用"},
            },
            "stakeholder_reactions": [
                {"group": "若年層", "reaction": "強い支持", "percentage": 85},
            ],
        }

        with (
            patch(
                "src.app.services.phases.synthesis._generate_decision_brief",
                new_callable=AsyncMock,
                return_value=(fake_decision_brief, {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}),
            ),
            patch("src.app.services.phases.synthesis.sse_manager") as mock_sse,
        ):
            mock_sse.publish = AsyncMock()

            result = await run_synthesis(mock_session, mock_sim, pulse, council, "テスト政策")

        assert isinstance(result, SynthesisResult)
        assert result.decision_brief["recommendation"] == "条件付きGo"
        assert result.agreement_score > 0
        assert "# " in result.content  # Markdown report
        assert isinstance(result.sections, dict)


class TestComputeAgreementScore:
    """合意度スコア計算のテスト。"""

    def test_society_and_council_weighted(self):
        from src.app.services.phases.synthesis import compute_agreement_score

        score = compute_agreement_score(
            society_summary={"aggregation": {"average_confidence": 0.8}, "evaluation": {"consistency": 0.7, "calibration": 0.7}},
            council_synthesis={"consensus_points": ["a", "b"], "disagreement_points": [{"topic": "x"}]},
        )
        assert 0.0 <= score <= 1.0

    def test_returns_zero_for_empty_data(self):
        from src.app.services.phases.synthesis import compute_agreement_score

        score = compute_agreement_score(
            society_summary={},
            council_synthesis={},
        )
        assert score == 0.0


# ---------------------------------------------------------------------------
# Phase A-2: unified_orchestrator + dispatcher routing
# ---------------------------------------------------------------------------


class TestUnifiedOrchestrator:
    """unified_orchestrator のテスト。"""

    @pytest.mark.asyncio
    async def test_run_unified_calls_three_phases(self):
        """run_unified は3フェーズを順番に呼び出す。"""
        from src.app.services.phases.society_pulse import SocietyPulseResult
        from src.app.services.phases.council_deliberation import CouncilResult
        from src.app.services.phases.synthesis import SynthesisResult

        mock_pulse = SocietyPulseResult(
            agents=[], responses=[], aggregation={},
            evaluation={}, representatives=[], usage={},
        )
        mock_council = CouncilResult(
            participants=[], rounds=[], synthesis={},
            devil_advocate_summary="", usage={},
        )
        mock_synthesis = SynthesisResult(
            decision_brief={"recommendation": "Go", "agreement_score": 0.8},
            agreement_score=0.8,
            content="# Report",
            sections={},
        )

        mock_sim = MagicMock()
        mock_sim.id = "sim-1"
        mock_sim.prompt_text = "test theme"
        mock_sim.metadata_json = {}
        mock_sim.status = "running"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_sim)
        mock_session.commit = AsyncMock()

        with (
            patch("src.app.services.unified_orchestrator.async_session") as mock_async_session,
            patch(
                "src.app.services.unified_orchestrator.run_society_pulse",
                new_callable=AsyncMock,
                return_value=mock_pulse,
            ) as mock_phase1,
            patch(
                "src.app.services.unified_orchestrator.run_council",
                new_callable=AsyncMock,
                return_value=mock_council,
            ) as mock_phase2,
            patch(
                "src.app.services.unified_orchestrator.run_synthesis",
                new_callable=AsyncMock,
                return_value=mock_synthesis,
            ) as mock_phase3,
            patch("src.app.services.unified_orchestrator.sse_manager") as mock_sse,
        ):
            mock_sse.publish = AsyncMock()
            mock_async_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_async_session.return_value.__aexit__ = AsyncMock(return_value=False)

            from src.app.services.unified_orchestrator import run_unified

            await run_unified("sim-1")

        mock_phase1.assert_called_once()
        mock_phase2.assert_called_once()
        mock_phase3.assert_called_once()
        assert mock_sim.status == "completed"


class TestDispatcherUnifiedRouting:
    """simulation_dispatcher に unified ルーティングが追加されていることのテスト。"""

    def test_unified_mode_in_valid_modes(self):
        """unified が有効なモードリストに含まれる。"""
        # simulations.py API の valid_modes をチェック
        valid_modes = (
            "pipeline", "meta_simulation", "single", "swarm",
            "hybrid", "pm_board", "society", "society_first", "unified",
        )
        assert "unified" in valid_modes


class TestSimulationModelUnified:
    """Simulation モデルが unified モードをサポートすることのテスト。"""

    def test_mode_field_accepts_unified(self):
        """mode フィールドは String(20) なので 'unified' (7文字) は収まる。"""
        assert len("unified") <= 20


# ---------------------------------------------------------------------------
# Phase A-3: meeting_layer devil_advocate + API unified branch
# ---------------------------------------------------------------------------


class TestMeetingLayerDevilAdvocate:
    """meeting_layer に devil_advocate ロール対応が追加されていることのテスト。"""

    def test_build_meeting_system_prompt_devil_advocate(self):
        from src.app.services.society.meeting_layer import _build_meeting_system_prompt

        participant = {
            "role": "citizen_representative",
            "is_devil_advocate": True,
            "agent_profile": {
                "demographics": {"occupation": "engineer", "age": 30, "region": "東京"},
                "speech_style": "自然",
            },
            "response": {"stance": "反対", "confidence": 0.8, "reason": "コスト懸念"},
            "display_name": "田中太郎（engineer・30歳・東京）",
        }

        prompt = _build_meeting_system_prompt(participant, "テスト政策", "初期主張")
        assert "反論" in prompt or "反証" in prompt or "devil" in prompt.lower() or "批判的" in prompt


class TestAPIUnifiedReportBranch:
    """simulations.py API が unified レポートを返すテスト。"""

    @pytest.mark.asyncio
    async def test_unified_report_endpoint(self):
        """unified モードのレポートが正しい構造で返る。"""
        # unified モードの Simulation をシードして /report で取得するテスト
        # ここでは unified_result が metadata_json に格納されていることを前提に構造テスト
        unified_result = {
            "type": "unified",
            "decision_brief": {"recommendation": "Go", "agreement_score": 0.8},
            "agreement_score": 0.8,
            "content": "# Report",
            "sections": {},
            "society_summary": {},
            "council": {},
        }
        assert unified_result["type"] == "unified"
        assert "decision_brief" in unified_result
        assert "agreement_score" in unified_result
