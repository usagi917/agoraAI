"""ConversationLog の保存ヘルパー。"""

from inspect import isawaitable
import logging
from typing import Any, Iterable

from src.app.models.conversation_log import (
    CONVERSATION_LOG_ADDRESSED_TO_MAX_LENGTH,
    CONVERSATION_LOG_PARTICIPANT_NAME_MAX_LENGTH,
    CONVERSATION_LOG_PARTICIPANT_ROLE_MAX_LENGTH,
    CONVERSATION_LOG_PHASE_MAX_LENGTH,
    CONVERSATION_LOG_STANCE_MAX_LENGTH,
    ConversationLog,
)

logger = logging.getLogger(__name__)


def _clip_text(value: Any, max_length: int) -> str:
    text = str(value or "")
    return text[:max_length]


def normalize_conversation_log_entry(entry: ConversationLog) -> ConversationLog:
    """DB 制約に合わせて可変長フィールドを正規化する。"""
    entry.phase = _clip_text(entry.phase, CONVERSATION_LOG_PHASE_MAX_LENGTH)
    entry.participant_name = _clip_text(
        entry.participant_name,
        CONVERSATION_LOG_PARTICIPANT_NAME_MAX_LENGTH,
    )
    entry.participant_role = _clip_text(
        entry.participant_role,
        CONVERSATION_LOG_PARTICIPANT_ROLE_MAX_LENGTH,
    )
    entry.stance = _clip_text(entry.stance, CONVERSATION_LOG_STANCE_MAX_LENGTH)
    entry.addressed_to = _clip_text(
        entry.addressed_to,
        CONVERSATION_LOG_ADDRESSED_TO_MAX_LENGTH,
    )
    return entry


async def persist_conversation_logs(
    session: Any,
    entries: Iterable[ConversationLog],
    *,
    context: str,
) -> None:
    """会話ログ保存を savepoint に隔離して外側の transaction を汚さない。"""
    if not session:
        return

    normalized_entries = [normalize_conversation_log_entry(entry) for entry in entries]
    if not normalized_entries:
        return

    try:
        nested_transaction = session.begin_nested()
        if isawaitable(nested_transaction):
            nested_transaction = await nested_transaction

        async with nested_transaction:
            for entry in normalized_entries:
                add_result = session.add(entry)
                if isawaitable(add_result):
                    await add_result
            await session.flush()
    except Exception as e:
        logger.warning("Failed to save %s: %s", context, e)
