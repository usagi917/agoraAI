"""記憶圧縮: シミュレーション後にエージェントのメモリを更新する。

二層メモリアーキテクチャ:
- Layer A (rolling_summary): LLM で圧縮された性格傾向要約（~200字、固定サイズ）
- Layer B (episodes): テーマ付きエピソードリスト（JSON配列、MAX 50件 FIFO）
- Fallback (memory_summary): 従来の追記型テキスト（後方互換用）
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.agent_profile import AgentProfile

logger = logging.getLogger(__name__)

MAX_EPISODES = 50


# ---------------------------------------------------------------------------
# Legacy: compress_memory (後方互換のため保持)
# ---------------------------------------------------------------------------

def compress_memory(
    previous_summary: str,
    activation_response: dict,
    meeting_participation: dict | None = None,
) -> str:
    """エージェントの経験を圧縮して memory_summary を更新する。

    LLM は使用しない。構造化テキストに変換する。
    """
    parts = []

    if previous_summary:
        parts.append(previous_summary.strip())

    stance = activation_response.get("stance", "")
    confidence = activation_response.get("confidence", 0.5)
    reason = activation_response.get("reason", "")
    if stance:
        parts.append(f"[活性化] スタンス:{stance} 信頼度:{confidence:.0%} 理由:{reason}")

    if meeting_participation:
        role = meeting_participation.get("role", "")
        final_position = meeting_participation.get("final_position", "")
        if final_position:
            parts.append(f"[Meeting] 役割:{role} 最終立場:{final_position}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Layer B: エピソードビルダー
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    # 句点で切れるならそこまで
    for sep in ("。", ".", "、"):
        idx = text.find(sep, 0, max_len)
        if idx > 0:
            return text[: idx + 1]
    return text[:max_len]


def build_episode(
    theme: str,
    theme_category: str,
    activation_response: dict,
    meeting_participation: dict | None,
    sim_id: str,
) -> dict:
    """1回のシミュレーション結果からエピソード dict を作成する。"""
    reason = activation_response.get("reason", "")
    ep: dict = {
        "theme": _truncate(theme, 80),
        "theme_category": theme_category,
        "stance": activation_response.get("stance", ""),
        "confidence": activation_response.get("confidence", 0.5),
        "reason_digest": _truncate(reason, 80),
        "sim_id": sim_id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if meeting_participation:
        fp = meeting_participation.get("final_position", "")
        if fp:
            ep["final_position"] = fp
    return ep


def select_relevant_episodes(
    episodes: list[dict] | None,
    theme: str,
    theme_category: str,
    top_k: int = 3,
) -> list[dict]:
    """現テーマに最も関連するエピソードを top_k 件選択する。"""
    if not episodes:
        return []

    from src.app.services.society.agent_selector import TOPIC_KEYWORDS

    # 現テーマのトピックタグを抽出
    theme_lower = theme.lower()
    current_topics: set[str] = set()
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in theme_lower:
                current_topics.add(topic)
                break

    scored: list[tuple[float, int, dict]] = []
    for idx, ep in enumerate(episodes):
        score = 0.0

        # カテゴリ完全一致
        if ep.get("theme_category") == theme_category and theme_category != "unknown":
            score += 3.0

        # TOPIC_KEYWORDS によるキーワード重複
        ep_theme_lower = ep.get("theme", "").lower()
        ep_topics: set[str] = set()
        for topic, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in ep_theme_lower:
                    ep_topics.add(topic)
                    break
        score += len(current_topics & ep_topics) * 1.0

        # recency ブースト（新しいほど高い）
        score += idx * 0.1

        scored.append((score, idx, ep))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [ep for _, _, ep in scored[:top_k]]


# ---------------------------------------------------------------------------
# Layer A: ローリング要約（LLM 圧縮）
# ---------------------------------------------------------------------------

_ROLLING_SUMMARY_SYSTEM = (
    "あなたは人物分析アシスタントです。"
    "エージェントの経験から性格パターンを抽出し、簡潔な日本語要約を生成してください。"
)

_ROLLING_SUMMARY_USER = """\
【現在の性格要約】
{previous}

【最新の経験】
テーマ: {theme} ({category})
立場: {stance} (確信度: {confidence})
理由: {reason}

200文字以内で、このエージェントの判断傾向・価値観・行動パターンを要約してください。
具体的なテーマ名や日付は含めず、性格特性のみを記述してください。"""


async def compress_rolling_summary(
    previous_summary: str,
    latest_episode: dict,
    llm_client,
    provider: str = "openai",
) -> str:
    """過去の要約 + 最新エピソードから性格要約を LLM で再生成する。"""
    user_prompt = _ROLLING_SUMMARY_USER.format(
        previous=previous_summary or "（初回）",
        theme=latest_episode.get("theme", ""),
        category=latest_episode.get("theme_category", "unknown"),
        stance=latest_episode.get("stance", ""),
        confidence=latest_episode.get("confidence", 0.5),
        reason=latest_episode.get("reason_digest", ""),
    )
    try:
        result, _usage = await llm_client.call(
            provider,
            _ROLLING_SUMMARY_SYSTEM,
            user_prompt,
            temperature=0.3,
            max_tokens=256,
        )
        text = result if isinstance(result, str) else str(result)
        return text[:200]
    except Exception:
        logger.warning("Rolling summary LLM call failed, keeping previous summary")
        return previous_summary


# ---------------------------------------------------------------------------
# update_agent_memories (フラグ分岐付き)
# ---------------------------------------------------------------------------

async def update_agent_memories(
    session: AsyncSession,
    agents: list[dict],
    responses: list[dict],
    meeting_result: dict | None = None,
    *,
    theme: str = "",
    theme_category: str = "unknown",
    simulation_id: str = "",
    llm_client=None,
    accuracy_flags=None,
) -> int:
    """活性化結果を基にエージェントのメモリを更新する。

    Returns:
        更新されたエージェント数
    """
    use_episodes = accuracy_flags and accuracy_flags.is_enabled("episodic_memory")
    use_rolling = accuracy_flags and accuracy_flags.is_enabled("rolling_summary") and llm_client

    # Meeting 参加者のマッピング
    meeting_participants: dict[int, dict] = {}
    if meeting_result:
        for round_args in meeting_result.get("rounds", []):
            for arg in round_args:
                idx = arg.get("participant_index", -1)
                if idx >= 0:
                    meeting_participants[idx] = {
                        "role": arg.get("role", ""),
                        "final_position": arg.get("position", ""),
                    }

    updated = 0
    for i, (agent, resp) in enumerate(zip(agents, responses)):
        agent_id = agent.get("id")
        if not agent_id:
            continue

        meeting_data = meeting_participants.get(i)
        db_agent = await session.get(AgentProfile, agent_id)
        if not db_agent:
            continue

        changed = False

        # Layer B: エピソード追加
        if use_episodes:
            episode = build_episode(theme, theme_category, resp, meeting_data, simulation_id)
            current_episodes = list(agent.get("episodes") or [])
            current_episodes.append(episode)
            current_episodes = current_episodes[-MAX_EPISODES:]
            db_agent.episodes = current_episodes
            changed = True

            # Layer A: ローリング要約（エピソードが有効な場合のみ）
            if use_rolling:
                previous = agent.get("rolling_summary", "")
                new_rolling = await compress_rolling_summary(
                    previous, episode, llm_client,
                )
                db_agent.rolling_summary = new_rolling

        # Fallback: 従来の memory_summary も常に更新
        previous_mem = agent.get("memory_summary", "")
        new_summary = compress_memory(previous_mem, resp, meeting_data)
        if new_summary != previous_mem:
            db_agent.memory_summary = new_summary
            changed = True

        if changed:
            updated += 1

    if updated:
        await session.commit()

    logger.info("Updated memory for %d agents", updated)
    return updated
