"""Meeting Layer: 代表者+専門家による多ラウンド構造化議論"""

import asyncio
import logging
import uuid
from typing import Any

from src.app.config import settings
from src.app.llm.multi_client import multi_llm_client
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

# Meeting はフルBDIの代わりに、軽量な構造化議論プロトコルを使用
# Phase 2 では debate_protocol の3フェーズ構造を再現する

MEETING_ROUNDS = 3  # Claims → Counters → Synthesis


def _build_participant_context(participant: dict) -> str:
    """参加者のコンテキスト文字列を構築する。"""
    if participant["role"] == "expert":
        persona = participant.get("persona", {})
        return (
            f"【{participant.get('display_name', '専門家')}】\n"
            f"役割: {persona.get('role', '')}\n"
            f"焦点: {persona.get('focus', '')}\n"
            f"思考スタイル: {persona.get('thinking_style', '')}"
        )

    agent = participant["agent_profile"]
    demo = agent.get("demographics", {})
    resp = participant.get("response", {}) or {}
    return (
        f"【市民代表: {demo.get('occupation', '不明')}・{demo.get('age', '?')}歳・{demo.get('region', '不明')}】\n"
        f"スタンス: {resp.get('stance', '中立')} (信頼度: {resp.get('confidence', 0.5):.1%})\n"
        f"理由: {resp.get('reason', '')}\n"
        f"発話スタイル: {agent.get('speech_style', '自然')}"
    )


def _build_meeting_system_prompt(participant: dict, theme: str, round_name: str) -> str:
    """Meeting 用のシステムプロンプトを構築する。"""
    context = _build_participant_context(participant)

    if participant["role"] == "expert":
        prompts = participant.get("prompts", {})
        expert_instruction = prompts.get("analyze", "専門的知見に基づいて分析してください。")
        return (
            f"あなたは以下の専門家として議論に参加しています。\n\n"
            f"{context}\n\n"
            f"テーマ: {theme}\n\n"
            f"議論フェーズ: {round_name}\n\n"
            f"専門家としての指示:\n{expert_instruction}\n\n"
            f"回答はJSON形式で:\n"
            f'{{"position": "あなたの立場の要約", '
            f'"argument": "100-200文字の主張", '
            f'"evidence": "根拠となる事実やデータ", '
            f'"concerns": ["懸念事項"], '
            f'"questions_to_others": ["他の参加者への質問"]}}'
        )

    return (
        f"あなたは以下のプロフィールを持つ市民代表として議論に参加しています。\n\n"
        f"{context}\n\n"
        f"テーマ: {theme}\n\n"
        f"議論フェーズ: {round_name}\n\n"
        f"あなたのプロフィールと価値観に基づいて率直に議論してください。\n\n"
        f"回答はJSON形式で:\n"
        f'{{"position": "あなたの立場の要約", '
        f'"argument": "100-200文字の主張", '
        f'"evidence": "根拠となる事実や経験", '
        f'"concerns": ["懸念事項"], '
        f'"questions_to_others": ["他の参加者への質問"]}}'
    )


async def _run_meeting_round(
    participants: list[dict],
    theme: str,
    round_number: int,
    round_name: str,
    previous_arguments: list[dict],
    simulation_id: str | None = None,
) -> list[dict]:
    """Meeting の1ラウンドを実行する。"""
    multi_llm_client.initialize()

    # 前ラウンドの議論要約
    prev_summary = ""
    if previous_arguments:
        parts = []
        for arg in previous_arguments:
            name = arg.get("participant_name", "参加者")
            position = arg.get("position", "")
            argument = arg.get("argument", "")
            parts.append(f"- {name}: {position}。{argument}")
        prev_summary = "前ラウンドの議論:\n" + "\n".join(parts)

    calls = []
    for p in participants:
        system_prompt = _build_meeting_system_prompt(p, theme, round_name)
        user_prompt = f"テーマ「{theme}」について、あなたの立場から議論してください。"
        if prev_summary:
            user_prompt += f"\n\n{prev_summary}\n\n上記の議論を踏まえて回答してください。"

        calls.append({
            "provider": p["agent_profile"].get("llm_backend", "openai"),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": 0.7,
            "max_tokens": 2048,
        })

    results = await multi_llm_client.call_batch_by_provider(calls, max_concurrency=10)

    arguments = []
    for i, (result, usage) in enumerate(results):
        p = participants[i]
        name = p.get("display_name", "") or p["agent_profile"].get("demographics", {}).get("occupation", f"参加者{i+1}")

        if isinstance(result, dict):
            arg = {
                "participant_index": i,
                "participant_name": name,
                "role": p["role"],
                "expertise": p.get("expertise", ""),
                "round": round_number,
                "position": result.get("position", ""),
                "argument": result.get("argument", ""),
                "evidence": result.get("evidence", ""),
                "concerns": result.get("concerns", []),
                "questions_to_others": result.get("questions_to_others", []),
                "usage": usage,
            }
        else:
            arg = {
                "participant_index": i,
                "participant_name": name,
                "role": p["role"],
                "expertise": p.get("expertise", ""),
                "round": round_number,
                "position": str(result)[:200] if result else "",
                "argument": str(result)[:300] if result else "",
                "evidence": "",
                "concerns": [],
                "questions_to_others": [],
                "usage": usage,
            }
        arguments.append(arg)

    if simulation_id:
        await sse_manager.publish(simulation_id, "meeting_round_completed", {
            "round": round_number,
            "round_name": round_name,
            "argument_count": len(arguments),
        })

    return arguments


async def _run_synthesis(
    all_arguments: list[list[dict]],
    theme: str,
    participants: list[dict],
) -> tuple[dict, dict]:
    """議論の総括を生成する。"""
    multi_llm_client.initialize()

    # 全ラウンドの議論をまとめる
    discussion_parts = []
    for round_args in all_arguments:
        for arg in round_args:
            name = arg.get("participant_name", "参加者")
            role = arg.get("role", "")
            position = arg.get("position", "")
            argument = arg.get("argument", "")
            evidence = arg.get("evidence", "")
            discussion_parts.append(
                f"[{name} ({role})] 立場: {position}\n"
                f"  主張: {argument}\n"
                f"  根拠: {evidence}"
            )
    discussion_text = "\n\n".join(discussion_parts)

    system_prompt = (
        "あなたは会議のファシリテーターです。以下の議論を総括してください。\n\n"
        "出力はJSON形式で:\n"
        "{\n"
        '  "consensus_points": ["合意点1", "合意点2"],\n'
        '  "disagreement_points": [{"topic": "対立点", "positions": [{"participant": "名前", "position": "立場"}]}],\n'
        '  "key_insights": ["洞察1", "洞察2"],\n'
        '  "scenarios": [{"name": "シナリオ名", "description": "説明", "probability": 0.0-1.0, "key_factors": ["要因"]}],\n'
        '  "stance_shifts": [{"participant": "名前", "from": "変化前", "to": "変化後", "reason": "理由"}],\n'
        '  "recommendations": ["提言1", "提言2"],\n'
        '  "overall_assessment": "総合評価（200文字程度）"\n'
        "}"
    )

    user_prompt = f"テーマ: {theme}\n\n議論内容:\n{discussion_text}"

    result, usage = await multi_llm_client.call(
        provider_name="openai",  # 統合は高品質プロバイダ
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=4096,
    )

    if isinstance(result, dict):
        return result, usage

    return {
        "consensus_points": [],
        "disagreement_points": [],
        "key_insights": [],
        "scenarios": [],
        "stance_shifts": [],
        "recommendations": [],
        "overall_assessment": str(result)[:500] if result else "",
    }, usage


async def run_meeting(
    participants: list[dict],
    theme: str,
    simulation_id: str | None = None,
    num_rounds: int = 3,
) -> dict[str, Any]:
    """Meeting Layer を実行する。

    3ラウンド構成:
    1. Initial Claims: 各参加者の初期主張
    2. Cross-examination: 相互質疑・反論
    3. Final Positions: 最終立場表明

    Returns:
        {
            "rounds": list[list[dict]],  # 各ラウンドの議論
            "synthesis": dict,            # 総括
            "participants": list[dict],   # 参加者情報
            "usage": dict,                # トークン使用量
        }
    """
    round_names = ["初期主張", "相互質疑・反論", "最終立場表明"]
    if num_rounds > 3:
        round_names.extend([f"追加ラウンド{i}" for i in range(4, num_rounds + 1)])

    all_arguments: list[list[dict]] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if simulation_id:
        await sse_manager.publish(simulation_id, "meeting_started", {
            "participant_count": len(participants),
            "num_rounds": min(num_rounds, len(round_names)),
        })

    for round_idx in range(min(num_rounds, len(round_names))):
        round_name = round_names[round_idx]
        previous = all_arguments[-1] if all_arguments else []

        arguments = await _run_meeting_round(
            participants, theme, round_idx + 1, round_name,
            previous, simulation_id,
        )

        for arg in arguments:
            u = arg.get("usage", {})
            total_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += u.get("completion_tokens", 0)
            total_usage["total_tokens"] += u.get("total_tokens", 0)

        all_arguments.append(arguments)

    # 総括
    synthesis, synth_usage = await _run_synthesis(all_arguments, theme, participants)
    total_usage["prompt_tokens"] += synth_usage.get("prompt_tokens", 0)
    total_usage["completion_tokens"] += synth_usage.get("completion_tokens", 0)
    total_usage["total_tokens"] += synth_usage.get("total_tokens", 0)

    if simulation_id:
        await sse_manager.publish(simulation_id, "meeting_completed", {
            "rounds": len(all_arguments),
            "synthesis_available": bool(synthesis),
        })

    # 参加者サマリー（プロフィール詳細を除外）
    participant_summaries = []
    for p in participants:
        summary = {
            "role": p["role"],
            "expertise": p.get("expertise", ""),
            "display_name": p.get("display_name", ""),
        }
        if p["role"] == "citizen_representative":
            demo = p["agent_profile"].get("demographics", {})
            summary["display_name"] = f"{demo.get('occupation', '不明')}・{demo.get('age', '?')}歳"
            summary["stance"] = p.get("stance", "")
        participant_summaries.append(summary)

    logger.info(
        "Meeting completed: %d rounds, %d arguments total",
        len(all_arguments), sum(len(r) for r in all_arguments),
    )

    return {
        "rounds": all_arguments,
        "synthesis": synthesis,
        "participants": participant_summaries,
        "usage": total_usage,
    }
