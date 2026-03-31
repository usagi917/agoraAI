"""Meeting Layer テスト"""

import pytest
from unittest.mock import AsyncMock, patch

from src.app.sse.manager import sse_manager
from src.app.services.society import meeting_layer
from src.app.services.society.meeting_layer import (
    _build_participant_context,
    _build_meeting_system_prompt,
    _serialize_argument_for_stream,
    run_meeting,
)
from src.app.services.society.meeting_report import (
    generate_meeting_report,
    _extract_stance_shifts,
    _collect_all_concerns,
)


class TestBuildParticipantContext:
    def test_citizen_context(self):
        participant = {
            "role": "citizen_representative",
            "agent_profile": {
                "demographics": {"occupation": "エンジニア", "age": 35, "region": "関東（都市部）"},
                "speech_style": "分析的で論理的",
            },
            "response": {"stance": "賛成", "confidence": 0.8, "reason": "テスト理由"},
        }
        context = _build_participant_context(participant)
        assert "エンジニア" in context
        assert "35歳" in context
        assert "賛成" in context

    def test_expert_context(self):
        participant = {
            "role": "expert",
            "display_name": "経済学者",
            "agent_profile": {},
            "persona": {
                "role": "Economist",
                "focus": "経済的影響",
                "thinking_style": "データに基づく分析",
            },
        }
        context = _build_participant_context(participant)
        assert "経済学者" in context
        assert "Economist" in context


class TestBuildMeetingPrompt:
    def test_citizen_prompt_contains_json_instruction(self):
        participant = {
            "role": "citizen_representative",
            "agent_profile": {
                "demographics": {"occupation": "会社員", "age": 40, "region": "関西（都市部）",
                                  "education": "bachelor", "income_bracket": "upper_middle", "gender": "male"},
                "big_five": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
                "speech_style": "丁寧で慎重",
            },
            "response": {"stance": "反対", "confidence": 0.6, "reason": "コストが高い"},
        }
        prompt = _build_meeting_system_prompt(participant, "AI規制について", "初期主張")
        assert "JSON" in prompt
        assert "AI規制" in prompt

    def test_expert_prompt_includes_analysis_instructions(self):
        participant = {
            "role": "expert",
            "display_name": "技術専門家",
            "agent_profile": {},
            "persona": {"role": "Technologist", "focus": "技術", "thinking_style": "test"},
            "prompts": {"analyze": "技術的な観点で分析"},
        }
        prompt = _build_meeting_system_prompt(participant, "DX推進", "初期主張")
        assert "技術的な観点" in prompt


class TestExtractStanceShifts:
    def test_detects_shifts(self):
        rounds = [
            [{"participant_name": "Alice", "position": "賛成"}, {"participant_name": "Bob", "position": "反対"}],
            [{"participant_name": "Alice", "position": "条件付き賛成"}, {"participant_name": "Bob", "position": "反対"}],
        ]
        shifts = _extract_stance_shifts(rounds)
        assert len(shifts) == 1
        assert shifts[0]["participant"] == "Alice"

    def test_no_shifts(self):
        rounds = [
            [{"participant_name": "Alice", "position": "賛成"}],
            [{"participant_name": "Alice", "position": "賛成"}],
        ]
        shifts = _extract_stance_shifts(rounds)
        assert len(shifts) == 0


class TestCollectConcerns:
    def test_deduplicates(self):
        rounds = [
            [{"concerns": ["コスト", "安全"]}, {"concerns": ["コスト", "環境"]}],
            [{"concerns": ["コスト", "雇用"]}],
        ]
        concerns = _collect_all_concerns(rounds)
        assert len(concerns) == 4  # コスト, 安全, 環境, 雇用
        assert concerns[0] == "コスト"


class TestGenerateMeetingReport:
    def test_report_structure(self):
        meeting_result = {
            "rounds": [
                [
                    {"participant_name": "経済学者", "role": "expert", "round": 1, "position": "慎重に推進", "argument": "経済効果は大きい", "evidence": "GDPデータ", "concerns": ["コスト"]},
                    {"participant_name": "会社員", "role": "citizen_representative", "round": 1, "position": "反対", "argument": "負担が大きい", "evidence": "個人経験", "concerns": ["生活費"]},
                ],
            ],
            "synthesis": {
                "consensus_points": ["段階的導入が望ましい"],
                "disagreement_points": [{"topic": "コスト負担", "positions": []}],
                "key_insights": ["多角的検討が必要"],
                "scenarios": [{"name": "楽観シナリオ", "description": "成功ケース", "probability": 0.4}],
                "stance_shifts": [],
                "recommendations": ["段階的導入を推奨"],
                "overall_assessment": "議論は建設的に進んだ",
            },
            "participants": [
                {"role": "expert", "expertise": "economist", "display_name": "経済学者"},
                {"role": "citizen_representative", "expertise": "", "display_name": "会社員・40歳"},
            ],
        }
        report = generate_meeting_report(meeting_result)
        assert "summary" in report
        assert len(report["consensus_points"]) == 1
        assert len(report["scenarios"]) == 1
        assert len(report["key_arguments"]) == 2
        assert report["overall_assessment"] == "議論は建設的に進んだ"


class TestMeetingStreamPayloads:
    def test_serialize_argument_for_stream_includes_targeting_fields(self):
        payload = _serialize_argument_for_stream({
            "round": 2,
            "participant_name": "田中",
            "participant_index": 42,
            "role": "citizen_representative",
            "expertise": "",
            "position": "賛成",
            "argument": "コストと利便性を比較すべきです。",
            "evidence": "家計調査",
            "addressed_to": "佐藤",
            "addressed_to_participant_index": 7,
            "belief_update": "慎重に前進へ変更",
            "concerns": ["負担増"],
            "questions_to_others": ["佐藤さんは財源をどう見ますか"],
            "is_devil_advocate": True,
            "sub_round": "direct_exchange",
            "tension_topic": "財源",
        }, "相互質疑・反論")

        assert payload["participant_index"] == 42
        assert payload["addressed_to_participant_index"] == 7
        assert payload["is_devil_advocate"] is True
        assert payload["sub_round"] == "direct_exchange"

    @pytest.mark.asyncio
    async def test_run_meeting_round_uses_agent_index_and_devil_flag(self):
        participants = [{
            "role": "citizen_representative",
            "is_devil_advocate": True,
            "display_name": "田中太郎",
            "agent_profile": {
                "agent_index": 42,
                "llm_backend": "openai",
                "demographics": {"occupation": "会社員", "age": 35, "region": "東京"},
                "speech_style": "自然",
            },
            "response": {"stance": "賛成", "confidence": 0.8, "reason": "生活が便利になる"},
        }]

        fake_results = [({
            "position": "賛成",
            "argument": "生活面の便益が大きいと思います。",
            "evidence": "実体験",
            "addressed_to": "",
            "belief_update": "",
            "concerns": ["費用"],
            "questions_to_others": [],
        }, {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30})]

        with patch.object(meeting_layer.multi_llm_client, "initialize"), \
             patch.object(meeting_layer.multi_llm_client, "call_batch_by_provider", new=AsyncMock(return_value=fake_results)):
            arguments = await meeting_layer._run_meeting_round(
                participants,
                "テスト政策",
                1,
                "初期主張",
                [],
            )

        assert arguments[0]["participant_index"] == 42
        assert arguments[0]["is_devil_advocate"] is True

    @pytest.mark.asyncio
    async def test_run_meeting_publishes_round_snapshot_arguments(self):
        participants = [{
            "role": "citizen_representative",
            "display_name": "田中太郎",
            "agent_profile": {"agent_index": 42, "demographics": {}, "speech_style": "自然"},
            "response": {"stance": "賛成", "confidence": 0.8, "reason": "利便性"},
        }]
        round_args = [{
            "participant_index": 42,
            "participant_name": "田中太郎",
            "role": "citizen_representative",
            "expertise": "",
            "round": 1,
            "position": "賛成",
            "argument": "私は段階的導入が妥当だと思います。",
            "evidence": "家計データ",
            "addressed_to": "",
            "addressed_to_participant_index": None,
            "belief_update": "",
            "concerns": ["費用"],
            "questions_to_others": [],
            "is_devil_advocate": False,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }]

        with patch("src.app.services.society.meeting_layer._run_meeting_round", new=AsyncMock(return_value=round_args)), \
             patch("src.app.services.society.meeting_layer._run_synthesis", new=AsyncMock(return_value=({}, {}))), \
             patch.object(sse_manager, "publish", new=AsyncMock()) as publish_mock:
            await run_meeting(
                participants,
                "テスト政策",
                simulation_id="sim-1",
                num_rounds=1,
            )

        round_completed_calls = [
            call for call in publish_mock.await_args_list
            if call.args[1] == "meeting_round_completed"
        ]
        assert len(round_completed_calls) == 1

        payload = round_completed_calls[0].args[2]
        assert payload["round"] == 1
        assert payload["argument_count"] == 1
        assert payload["arguments"][0]["participant_index"] == 42
        assert payload["arguments"][0]["argument"] == round_args[0]["argument"]


class TestBalancedBriefing:
    def test_balanced_briefing_contains_pro_and_con(self):
        from src.app.services.society.meeting_layer import _build_balanced_briefing

        result = _build_balanced_briefing(
            "少子化対策",
            grounding_facts=[
                {"fact": "合計特殊出生率は1.2", "source": "厚生労働省2023"},
                {"fact": "子育て支援予算は2兆円", "source": "内閣府"},
            ],
        )
        assert "賛成" in result
        assert "反対" in result
        assert "少子化対策" in result

    def test_balanced_briefing_without_facts(self):
        from src.app.services.society.meeting_layer import _build_balanced_briefing

        result = _build_balanced_briefing("AI規制")
        assert "賛成" in result
        assert "反対" in result
        assert "AI規制" in result
        # grounding_facts なしの場合、関連データセクションは含まれない
        assert "関連データ" not in result

    def test_balanced_briefing_includes_grounding_facts(self):
        from src.app.services.society.meeting_layer import _build_balanced_briefing

        facts = [
            {"fact": "出生率1.2", "source": "厚生労働省"},
            {"fact": "子育てコスト増", "source": "内閣府"},
        ]
        result = _build_balanced_briefing("少子化対策", grounding_facts=facts)
        assert "関連データ" in result
        assert "出生率1.2" in result
        assert "厚生労働省" in result

    @pytest.mark.asyncio
    async def test_meeting_result_includes_briefing(self):
        participants = [{
            "role": "citizen_representative",
            "display_name": "田中太郎",
            "agent_profile": {
                "agent_index": 1,
                "demographics": {"occupation": "会社員", "age": 40, "region": "東京"},
                "speech_style": "自然",
            },
            "response": {"stance": "賛成", "confidence": 0.7, "reason": "生活向上"},
        }]
        round_args = [{
            "participant_index": 1,
            "participant_name": "田中太郎",
            "role": "citizen_representative",
            "expertise": "",
            "round": 1,
            "position": "賛成",
            "argument": "少子化対策は重要です。",
            "evidence": "",
            "addressed_to": "",
            "addressed_to_participant_index": None,
            "belief_update": "",
            "concerns": [],
            "questions_to_others": [],
            "is_devil_advocate": False,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }]

        with patch("src.app.services.society.meeting_layer._run_meeting_round", new=AsyncMock(return_value=round_args)), \
             patch("src.app.services.society.meeting_layer._run_synthesis", new=AsyncMock(return_value=({}, {}))), \
             patch.object(sse_manager, "publish", new=AsyncMock()):
            result = await run_meeting(
                participants,
                "少子化対策",
                simulation_id="sim-briefing-test",
                num_rounds=1,
            )

        assert "balanced_briefing" in result
        assert "少子化対策" in result["balanced_briefing"]
        assert "賛成" in result["balanced_briefing"]
        assert "反対" in result["balanced_briefing"]


# ===========================================================================
# Test: Cluster-Based Counter-Arguments
# ===========================================================================

class TestClusterCounterArguments:
    """Counter-arguments should be assigned based on opinion clusters from propagation."""

    def _make_participant(self, idx, stance="中立", confidence=0.5, is_devil=False, role="citizen_representative"):
        agent_profile = {
            "id": f"agent_{idx}",
            "agent_index": idx,
            "demographics": {"occupation": f"職業{idx}", "age": 30 + idx, "region": "関東"},
            "big_five": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
            "speech_style": "自然",
        }
        return {
            "role": role,
            "display_name": f"参加者{idx}",
            "is_devil_advocate": is_devil,
            "agent_profile": agent_profile,
            "response": {"stance": stance, "confidence": confidence, "reason": f"理由{idx}"},
        }

    def _make_activation_response(self, idx, stance="中立", confidence=0.5, reason="テスト理由"):
        return {
            "agent_id": f"agent_{idx}",
            "stance": stance,
            "confidence": confidence,
            "reason": reason,
        }

    def test_enrich_meeting_with_clusters_assigns_opposing_arguments(self):
        """Each participant should receive arguments from the opposing cluster."""
        from src.app.services.society.meeting_layer import enrich_meeting_with_clusters
        from src.app.services.society.opinion_dynamics import ClusterInfo

        participants = [
            self._make_participant(0, stance="賛成", confidence=0.9),
            self._make_participant(1, stance="反対", confidence=0.9),
        ]
        clusters = [
            ClusterInfo(label=0, member_ids=["agent_0", "agent_10"], centroid=[0.8], size=2),
            ClusterInfo(label=1, member_ids=["agent_1", "agent_11"], centroid=[0.2], size=2),
        ]
        activation_responses = [
            self._make_activation_response(0, stance="賛成", confidence=0.9, reason="経済成長に貢献する"),
            self._make_activation_response(1, stance="反対", confidence=0.9, reason="コストが高すぎる"),
            self._make_activation_response(10, stance="賛成", confidence=0.8, reason="雇用が増える"),
            self._make_activation_response(11, stance="反対", confidence=0.85, reason="地方の負担が大きい"),
        ]

        enriched = enrich_meeting_with_clusters(participants, clusters, activation_responses)

        # Agent 0 (cluster 0/賛成) should get arguments from cluster 1 (反対)
        assert "opposing_arguments" in enriched[0]
        opposing_0 = enriched[0]["opposing_arguments"]
        assert len(opposing_0) > 0
        # Opposing arguments should come from 反対 cluster members
        opposing_texts = [a["reason"] for a in opposing_0]
        assert any("コスト" in t or "負担" in t for t in opposing_texts)

        # Agent 1 (cluster 1/反対) should get arguments from cluster 0 (賛成)
        assert "opposing_arguments" in enriched[1]
        opposing_1 = enriched[1]["opposing_arguments"]
        assert len(opposing_1) > 0
        opposing_texts_1 = [a["reason"] for a in opposing_1]
        assert any("経済" in t or "雇用" in t for t in opposing_texts_1)

    def test_devil_advocate_gets_arguments_from_all_opposing_clusters(self):
        """Devil's advocate should receive arguments from ALL clusters they're NOT in."""
        from src.app.services.society.meeting_layer import enrich_meeting_with_clusters
        from src.app.services.society.opinion_dynamics import ClusterInfo

        participants = [
            self._make_participant(0, stance="賛成", confidence=0.9, is_devil=True),
        ]
        clusters = [
            ClusterInfo(label=0, member_ids=["agent_0"], centroid=[0.8], size=1),
            ClusterInfo(label=1, member_ids=["agent_5"], centroid=[0.5], size=1),
            ClusterInfo(label=2, member_ids=["agent_6"], centroid=[0.2], size=1),
        ]
        activation_responses = [
            self._make_activation_response(0, stance="賛成", confidence=0.9, reason="成長"),
            self._make_activation_response(5, stance="中立", confidence=0.6, reason="中立的な見解"),
            self._make_activation_response(6, stance="反対", confidence=0.8, reason="反対の理由"),
        ]

        enriched = enrich_meeting_with_clusters(participants, clusters, activation_responses)

        # Devil's advocate in cluster 0 should get args from clusters 1 AND 2
        opposing = enriched[0]["opposing_arguments"]
        reasons = [a["reason"] for a in opposing]
        assert any("中立" in r for r in reasons)
        assert any("反対" in r for r in reasons)

    def test_enrich_falls_back_when_no_clusters(self):
        """When no clusters are provided, participants should have empty opposing_arguments."""
        from src.app.services.society.meeting_layer import enrich_meeting_with_clusters

        participants = [
            self._make_participant(0, stance="賛成", confidence=0.9),
        ]

        enriched = enrich_meeting_with_clusters(participants, [], [])
        assert enriched[0].get("opposing_arguments", []) == []

    def test_enrich_falls_back_when_clusters_is_none(self):
        """When clusters is None, should return participants unchanged."""
        from src.app.services.society.meeting_layer import enrich_meeting_with_clusters

        participants = [
            self._make_participant(0, stance="賛成", confidence=0.9),
        ]

        enriched = enrich_meeting_with_clusters(participants, None, [])
        assert enriched[0].get("opposing_arguments", []) == []

    def test_meeting_prompt_includes_opposing_arguments_when_available(self):
        """System prompt should include opposing arguments section when present."""
        participant = {
            "role": "citizen_representative",
            "agent_profile": {
                "demographics": {"occupation": "会社員", "age": 40, "region": "東京"},
                "big_five": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
                "speech_style": "自然",
            },
            "response": {"stance": "賛成", "confidence": 0.8, "reason": "経済的に良い"},
            "opposing_arguments": [
                {"reason": "コスト負担が大きい", "confidence": 0.9, "stance": "反対"},
                {"reason": "地方格差が広がる", "confidence": 0.8, "stance": "反対"},
            ],
        }

        prompt = _build_meeting_system_prompt(participant, "テスト政策", "初期主張")
        assert "対立するグループ" in prompt
        assert "コスト負担が大きい" in prompt
        assert "地方格差が広がる" in prompt

    def test_meeting_prompt_no_opposing_section_without_arguments(self):
        """System prompt should NOT include opposing section when no arguments are present."""
        participant = {
            "role": "citizen_representative",
            "agent_profile": {
                "demographics": {"occupation": "会社員", "age": 40, "region": "東京"},
                "big_five": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
                "speech_style": "自然",
            },
            "response": {"stance": "賛成", "confidence": 0.8, "reason": "経済的に良い"},
        }

        prompt = _build_meeting_system_prompt(participant, "テスト政策", "初期主張")
        assert "対立するグループ" not in prompt
