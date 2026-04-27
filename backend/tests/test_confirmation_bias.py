"""P3-3: 確証バイアスプロンプトのテスト"""

import pytest


class TestConfirmationBiasPrompt:
    """確証バイアステンプレートのテスト."""

    def test_high_openness_low_bias(self):
        """高 Openness → バイアス弱い（or バイアスなし）."""
        from src.app.services.society.activation_prompts import build_confirmation_bias_instruction

        instruction = build_confirmation_bias_instruction(openness=0.9)
        # 高 Openness: バイアスが弱いか空
        assert len(instruction) < 100  # 短い or 空

    def test_low_openness_strong_bias(self):
        """低 Openness → 強い確証バイアスプロンプト."""
        from src.app.services.society.activation_prompts import build_confirmation_bias_instruction

        instruction = build_confirmation_bias_instruction(openness=0.1)
        assert len(instruction) > 20  # 具体的な指示がある
        assert "既存" in instruction or "確認" in instruction or "一致" in instruction

    def test_moderate_openness(self):
        """中程度の Openness → 軽度のバイアス."""
        from src.app.services.society.activation_prompts import build_confirmation_bias_instruction

        instruction = build_confirmation_bias_instruction(openness=0.5)
        # 何かしらの指示があるが、低 Openness よりは短い
        low_instruction = build_confirmation_bias_instruction(openness=0.1)
        assert len(instruction) <= len(low_instruction)

    def test_bias_strength_monotonic(self):
        """Openness が低いほどバイアス指示が長い（単調性）."""
        from src.app.services.society.activation_prompts import build_confirmation_bias_instruction

        lengths = [len(build_confirmation_bias_instruction(o)) for o in [0.1, 0.3, 0.5, 0.7, 0.9]]
        # 概ね単調減少（同値は許容）
        assert lengths[0] >= lengths[-1]
