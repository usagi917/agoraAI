"""Meeting Layer テスト"""

import pytest
from unittest.mock import AsyncMock, patch

from src.app.services.society.meeting_layer import (
    _build_participant_context,
    _build_meeting_system_prompt,
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
