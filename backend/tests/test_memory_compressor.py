"""記憶圧縮テスト"""

import pytest

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


# === Phase 1: スキーマ + フィーチャーフラグ ===


class TestAgentProfileNewColumns:
    """rolling_summary と episodes カラムが存在すること。"""

    def test_agent_profile_has_rolling_summary(self):
        from src.app.models.agent_profile import AgentProfile

        assert hasattr(AgentProfile, "rolling_summary")

    def test_agent_profile_has_episodes(self):
        from src.app.models.agent_profile import AgentProfile

        assert hasattr(AgentProfile, "episodes")


class TestFeatureFlagsRegistered:
    """episodic_memory / rolling_summary フラグが KNOWN_FEATURES に含まれること。"""

    def test_episodic_memory_flag(self):
        from src.app.services.society.accuracy_config import KNOWN_FEATURES

        assert "episodic_memory" in KNOWN_FEATURES

    def test_rolling_summary_flag(self):
        from src.app.services.society.accuracy_config import KNOWN_FEATURES

        assert "rolling_summary" in KNOWN_FEATURES


# === Phase 2: エピソードビルダー ===


class TestBuildEpisode:
    """build_episode() のテスト。"""

    def test_basic(self):
        from src.app.services.society.memory_compressor import build_episode

        ep = build_episode(
            theme="原発再稼働の是非",
            theme_category="energy",
            activation_response={"stance": "反対", "confidence": 0.85, "reason": "安全性に懸念がある"},
            meeting_participation=None,
            sim_id="sim-001",
        )
        assert ep["theme"] == "原発再稼働の是非"
        assert ep["theme_category"] == "energy"
        assert ep["stance"] == "反対"
        assert ep["confidence"] == 0.85
        assert ep["sim_id"] == "sim-001"
        assert "created_at" in ep
        assert len(ep["reason_digest"]) <= 80

    def test_reason_digest_truncation(self):
        from src.app.services.society.memory_compressor import build_episode

        long_reason = "あ" * 200
        ep = build_episode(
            theme="テスト",
            theme_category="unknown",
            activation_response={"stance": "中立", "confidence": 0.5, "reason": long_reason},
            meeting_participation=None,
            sim_id="sim-002",
        )
        assert len(ep["reason_digest"]) <= 80

    def test_theme_truncation(self):
        from src.app.services.society.memory_compressor import build_episode

        long_theme = "テーマ" * 50
        ep = build_episode(
            theme=long_theme,
            theme_category="unknown",
            activation_response={"stance": "賛成", "confidence": 0.7, "reason": "理由"},
            meeting_participation=None,
            sim_id="sim-003",
        )
        assert len(ep["theme"]) <= 80

    def test_with_meeting(self):
        from src.app.services.society.memory_compressor import build_episode

        ep = build_episode(
            theme="最低賃金",
            theme_category="economy",
            activation_response={"stance": "賛成", "confidence": 0.9, "reason": "生活改善"},
            meeting_participation={"role": "citizen_representative", "final_position": "条件付き賛成"},
            sim_id="sim-004",
        )
        assert ep["final_position"] == "条件付き賛成"

    def test_empty_inputs(self):
        from src.app.services.society.memory_compressor import build_episode

        ep = build_episode(
            theme="",
            theme_category="unknown",
            activation_response={},
            meeting_participation=None,
            sim_id="",
        )
        assert ep["stance"] == ""
        assert ep["confidence"] == 0.5


class TestSelectRelevantEpisodes:
    """select_relevant_episodes() のテスト。"""

    @pytest.fixture()
    def episodes(self):
        return [
            {"theme": "原発再稼働", "theme_category": "energy", "stance": "反対", "confidence": 0.8, "reason_digest": "安全", "sim_id": "1", "created_at": "2026-01-01T00:00:00"},
            {"theme": "最低賃金引上げ", "theme_category": "economy", "stance": "賛成", "confidence": 0.9, "reason_digest": "生活", "sim_id": "2", "created_at": "2026-02-01T00:00:00"},
            {"theme": "AI規制", "theme_category": "technology", "stance": "条件付き賛成", "confidence": 0.6, "reason_digest": "バランス", "sim_id": "3", "created_at": "2026-03-01T00:00:00"},
            {"theme": "消費税増税", "theme_category": "economy", "stance": "反対", "confidence": 0.7, "reason_digest": "負担", "sim_id": "4", "created_at": "2026-04-01T00:00:00"},
        ]

    def test_same_category_ranked_higher(self, episodes):
        from src.app.services.society.memory_compressor import select_relevant_episodes

        result = select_relevant_episodes(episodes, theme="法人税改革", theme_category="economy", top_k=2)
        categories = [ep["theme_category"] for ep in result]
        assert categories.count("economy") == 2

    def test_top_k_limit(self, episodes):
        from src.app.services.society.memory_compressor import select_relevant_episodes

        result = select_relevant_episodes(episodes, theme="テスト", theme_category="unknown", top_k=2)
        assert len(result) <= 2

    def test_empty_episodes(self):
        from src.app.services.society.memory_compressor import select_relevant_episodes

        assert select_relevant_episodes(None, "テスト", "unknown") == []
        assert select_relevant_episodes([], "テスト", "unknown") == []

    def test_keyword_overlap_boosts_score(self, episodes):
        from src.app.services.society.memory_compressor import select_relevant_episodes

        result = select_relevant_episodes(episodes, theme="エネルギー政策と原発", theme_category="unknown", top_k=1)
        # "原発" キーワードが重複するので energy のエピソードが上位に来るはず
        assert result[0]["theme_category"] == "energy"


# === Phase 3: ローリング要約 ===


class TestCompressRollingSummary:
    """compress_rolling_summary() のテスト。"""

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self):
        from unittest.mock import AsyncMock
        from src.app.services.society.memory_compressor import compress_rolling_summary

        mock_client = AsyncMock()
        mock_client.call.side_effect = RuntimeError("LLM unavailable")

        result = await compress_rolling_summary(
            previous_summary="経済優先で判断する傾向",
            latest_episode={"theme": "テスト", "theme_category": "unknown", "stance": "賛成", "confidence": 0.7, "reason_digest": "理由"},
            llm_client=mock_client,
        )
        # LLM 失敗時は前の要約をそのまま返す
        assert result == "経済優先で判断する傾向"

    @pytest.mark.asyncio
    async def test_length_cap(self):
        from unittest.mock import AsyncMock
        from src.app.services.society.memory_compressor import compress_rolling_summary

        mock_client = AsyncMock()
        long_output = "あ" * 300
        mock_client.call.return_value = (long_output, {"total_tokens": 100})

        result = await compress_rolling_summary(
            previous_summary="",
            latest_episode={"theme": "テスト", "theme_category": "unknown", "stance": "賛成", "confidence": 0.7, "reason_digest": "理由"},
            llm_client=mock_client,
        )
        assert len(result) <= 200
