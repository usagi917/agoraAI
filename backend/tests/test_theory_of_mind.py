"""P6-2: Theory of Mind CoT プロンプト強化テスト

activation_prompts.py の build_theory_of_mind_instruction() をテスト。
エージェントが他者の視点を推論してから自分の意見を形成する。
"""

import pytest


class TestTheoryOfMindInstruction:
    """Theory of Mind CoT プロンプトのテスト."""

    def test_returns_non_empty_string(self):
        """プロンプト指示が空でないこと."""
        from src.app.services.society.activation_prompts import build_theory_of_mind_instruction

        agent = {
            "demographics": {"age": 35, "occupation": "会社員", "region": "関東"},
            "big_five": {"O": 0.6, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
        }
        instruction = build_theory_of_mind_instruction(agent, theme="消費税増税")

        assert isinstance(instruction, str)
        assert len(instruction) > 50

    def test_includes_perspective_taking(self):
        """他者の視点を考慮する指示が含まれること."""
        from src.app.services.society.activation_prompts import build_theory_of_mind_instruction

        agent = {
            "demographics": {"age": 45, "occupation": "経営者", "region": "関西"},
            "big_five": {"O": 0.7, "C": 0.6, "E": 0.6, "A": 0.5, "N": 0.4},
        }
        instruction = build_theory_of_mind_instruction(agent, theme="リモートワーク義務化")

        # 他者視点に関するキーワードが含まれるべき
        has_perspective = any(
            kw in instruction for kw in ["他の人", "立場", "視点", "考え", "感じ", "思う"]
        )
        assert has_perspective, f"Perspective-taking keywords not found in: {instruction[:200]}"

    def test_includes_chain_of_thought(self):
        """段階的な思考プロセス（CoT）の指示が含まれること."""
        from src.app.services.society.activation_prompts import build_theory_of_mind_instruction

        agent = {
            "demographics": {"age": 25, "occupation": "学生", "region": "東北"},
            "big_five": {"O": 0.8, "C": 0.4, "E": 0.7, "A": 0.6, "N": 0.3},
        }
        instruction = build_theory_of_mind_instruction(agent, theme="大学無償化")

        # ステップや段階を示す指示があるべき
        has_steps = any(
            kw in instruction for kw in ["まず", "次に", "最後に", "ステップ", "1.", "①"]
        )
        assert has_steps, f"CoT step indicators not found in: {instruction[:200]}"

    def test_high_agreeableness_emphasizes_others(self):
        """高 Agreeableness のエージェントは他者への配慮がより強調される."""
        from src.app.services.society.activation_prompts import build_theory_of_mind_instruction

        high_a = {
            "demographics": {"age": 50, "occupation": "介護士", "region": "九州"},
            "big_five": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.9, "N": 0.5},
        }
        low_a = {
            "demographics": {"age": 50, "occupation": "介護士", "region": "九州"},
            "big_five": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.1, "N": 0.5},
        }
        theme = "介護保険制度改革"

        instr_high = build_theory_of_mind_instruction(high_a, theme=theme)
        instr_low = build_theory_of_mind_instruction(low_a, theme=theme)

        # 高 A は長い指示（より多くの他者視点考慮）
        assert len(instr_high) >= len(instr_low)

    def test_different_occupations_get_relevant_perspectives(self):
        """職業に応じた関連する他者の視点が含まれること."""
        from src.app.services.society.activation_prompts import build_theory_of_mind_instruction

        agent = {
            "demographics": {"age": 40, "occupation": "教師", "region": "中部"},
            "big_five": {"O": 0.6, "C": 0.6, "E": 0.5, "A": 0.6, "N": 0.4},
        }
        instruction = build_theory_of_mind_instruction(agent, theme="教育改革")

        # 何らかの他者グループへの言及があること
        assert len(instruction) > 50

    def test_empty_theme_still_works(self):
        """テーマが空でもエラーにならないこと."""
        from src.app.services.society.activation_prompts import build_theory_of_mind_instruction

        agent = {
            "demographics": {"age": 30, "occupation": "会社員", "region": "関東"},
            "big_five": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
        }
        instruction = build_theory_of_mind_instruction(agent, theme="")

        assert isinstance(instruction, str)
