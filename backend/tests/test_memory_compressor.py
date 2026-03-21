"""記憶圧縮テスト"""

from src.app.services.society.memory_compressor import compress_memory


class TestCompressMemory:
    def test_new_memory(self):
        result = compress_memory(
            "",
            {"stance": "賛成", "confidence": 0.8, "reason": "経済的メリット"},
        )
        assert "賛成" in result
        assert "80%" in result
        assert "経済的メリット" in result

    def test_append_to_existing(self):
        result = compress_memory(
            "[活性化] スタンス:反対 信頼度:70%",
            {"stance": "条件付き賛成", "confidence": 0.6, "reason": "条件次第"},
        )
        assert "反対" in result  # previous
        assert "条件付き賛成" in result  # new

    def test_with_meeting(self):
        result = compress_memory(
            "",
            {"stance": "中立", "confidence": 0.5, "reason": ""},
            meeting_participation={"role": "citizen_representative", "final_position": "段階的賛成"},
        )
        assert "Meeting" in result
        assert "段階的賛成" in result

    def test_empty_inputs(self):
        result = compress_memory("", {})
        assert result == ""
