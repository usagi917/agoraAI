"""会話ハイライト抽出: 議論の中から最もインパクトのある瞬間を特定する"""

import logging

from src.app.llm.multi_client import multi_llm_client

logger = logging.getLogger(__name__)


async def extract_conversation_highlights(
    rounds: list[list[dict]],
    synthesis: dict,
    theme: str,
) -> dict:
    """会議の全ラウンドからハイライトを抽出する。

    Returns:
        {
            "turning_point": {"participant": str, "round": int, "moment": str, "impact": str},
            "strongest_exchange": {"participants": [str], "topic": str, "summary": str},
            "most_cited_evidence": {"source": str, "content": str, "cited_by": [str]},
            "key_quotes": [{"speaker": str, "quote": str, "round": int}],
            "belief_journeys": [{"participant": str, "start": str, "end": str, "story": str}],
        }
    """
    multi_llm_client.initialize()

    # 全ラウンドの議論テキストを構築
    discussion_parts = []
    for round_idx, round_args in enumerate(rounds):
        round_num = round_idx + 1
        discussion_parts.append(f"=== ラウンド{round_num} ===")
        for arg in round_args:
            name = arg.get("participant_name", "?")
            role = arg.get("role", "")
            position = arg.get("position", "")
            argument = arg.get("argument", "")
            belief_update = arg.get("belief_update", "")
            addressed_to = arg.get("addressed_to", "")
            sub_round = arg.get("sub_round", "")

            label = f"[{name} ({role})"
            if sub_round == "direct_exchange":
                label += " → 直接対話"
            label += "]"

            parts = [f"{label} 立場: {position}"]
            if addressed_to:
                parts.append(f"  → {addressed_to}への応答")
            parts.append(f"  {argument}")
            if belief_update:
                parts.append(f"  【信念変化】{belief_update}")
            discussion_parts.append("\n".join(parts))
        discussion_parts.append("")

    discussion_text = "\n".join(discussion_parts)

    # スタンス変化
    stance_shifts = synthesis.get("stance_shifts", [])
    most_persuasive = synthesis.get("most_persuasive_argument", {})

    system_prompt = (
        "あなたは議論のハイライトを抽出するジャーナリストです。\n"
        "以下の会議記録から、読者が最も興味を持つハイライトを抽出してください。\n\n"
        "出力はJSON形式のみで:\n"
        "{\n"
        '  "turning_point": {"participant": "名前", "round": 数字, "moment": "何が起きたか（100文字）", "impact": "議論にどう影響したか（100文字）"},\n'
        '  "strongest_exchange": {"participants": ["名前A", "名前B"], "topic": "論点", "summary": "やり取りの要約（200文字）"},\n'
        '  "key_quotes": [{"speaker": "名前", "quote": "印象的な発言（原文尊重、100-200文字）", "round": 数字}],\n'
        '  "belief_journeys": [{"participant": "名前", "start": "当初の立場", "end": "最終的な立場", "story": "変化の物語（150-300文字）"}],\n'
        '  "dramatic_tension": "この議論で最も緊張感があった瞬間の描写（200文字）"\n'
        "}"
    )

    user_prompt = (
        f"テーマ: {theme}\n\n"
        f"会議記録:\n{discussion_text[:6000]}\n\n"
        f"スタンス変化: {stance_shifts}\n"
        f"最も説得力があった主張: {most_persuasive}\n"
    )

    try:
        result, usage = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.4,
            max_tokens=3072,
        )
        if isinstance(result, dict):
            logger.info("Conversation highlights extracted successfully")
            return result
    except Exception as e:
        logger.warning("Highlight extraction failed: %s", e)

    return {
        "turning_point": {},
        "strongest_exchange": {},
        "key_quotes": [],
        "belief_journeys": [],
        "dramatic_tension": "",
    }
