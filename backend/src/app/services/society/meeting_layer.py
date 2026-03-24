"""Meeting Layer: 代表者+専門家による多ラウンド構造化議論"""

import asyncio
import logging
import uuid
from typing import Any

from src.app.config import settings
from src.app.llm.multi_client import multi_llm_client
from src.app.models.conversation_log import ConversationLog
from src.app.services.conversation_log_store import persist_conversation_logs
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
    concern = resp.get("concern", "")
    priority = resp.get("priority", "")
    extra_parts = []
    if concern:
        extra_parts.append(f"最大の懸念: {concern}")
    if priority:
        extra_parts.append(f"重視すること: {priority}")
    extra_text = "\n".join(extra_parts)
    return (
        f"【市民代表: {demo.get('occupation', '不明')}・{demo.get('age', '?')}歳・{demo.get('region', '不明')}】\n"
        f"スタンス: {resp.get('stance', '中立')} (信頼度: {resp.get('confidence', 0.5):.1%})\n"
        f"理由: {resp.get('reason', '')}\n"
        f"{extra_text}\n"
        f"発話スタイル: {agent.get('speech_style', '自然')}"
    )


def _build_meeting_system_prompt(participant: dict, theme: str, round_name: str) -> str:
    """Meeting 用のシステムプロンプトを構築する。"""
    context = _build_participant_context(participant)
    is_devil_advocate = participant.get("is_devil_advocate", False)

    devil_advocate_instruction = (
        "\n\n【反証役】あなたは意図的に主流意見への反論を提示する役割です。"
        "最も強力な反証を探し、批判的に検証してください。"
        "他の参加者が見落としているリスクや前提の誤りを指摘してください。"
    ) if is_devil_advocate else ""

    json_format = (
        "回答はJSON形式で:\n"
        "{\n"
        '  "position": "あなたの立場の要約（1文）",\n'
        '  "argument": "300-600文字の主張。自然な言葉で段落として書いてください。'
        "あなたの経験・知識に基づく具体的な論拠を含めること。"
        '抽象的な一般論は禁止。",\n'
        '  "evidence": "根拠となる事実・データ・実体験",\n'
        '  "addressed_to": "応答先の参加者名（ラウンド2以降。ラウンド1は空文字）",\n'
        '  "belief_update": "前ラウンドから立場が変わった場合、何に説得されたかを記述（変化なしなら空文字）",\n'
        '  "concerns": ["懸念事項"],\n'
        '  "questions_to_others": ["他の参加者への具体的な質問"]\n'
        "}"
    )

    if participant["role"] == "expert":
        prompts = participant.get("prompts", {})
        expert_instruction = prompts.get("analyze", "専門的知見に基づいて分析してください。")
        return (
            f"あなたは以下の専門家として議論に参加しています。\n\n"
            f"{context}\n\n"
            f"テーマ: {theme}\n\n"
            f"議論フェーズ: {round_name}\n\n"
            f"専門家としての指示:\n{expert_instruction}"
            f"{devil_advocate_instruction}\n\n"
            f"{json_format}"
        )

    belief_update_instruction = (
        "\n\n【信念更新について】他の参加者の主張が説得力がある場合、あなたの立場を修正することは"
        "知的誠実さの表れです。頑なに初期立場を維持する必要はありません。"
        "ただし、変えた場合はその理由を明記してください。"
    )

    return (
        f"あなたは以下のプロフィールを持つ市民代表として議論に参加しています。\n\n"
        f"{context}\n\n"
        f"テーマ: {theme}\n\n"
        f"議論フェーズ: {round_name}\n\n"
        f"あなたのプロフィールと価値観に基づいて率直に議論してください。"
        f"{devil_advocate_instruction}"
        f"{belief_update_instruction}\n\n"
        f"{json_format}"
    )


async def _run_meeting_round(
    participants: list[dict],
    theme: str,
    round_number: int,
    round_name: str,
    previous_arguments: list[dict],
    simulation_id: str | None = None,
    session: Any = None,
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

    # ラウンド別の指示を構築
    round_instructions = {
        1: (
            f"テーマ「{theme}」について、あなたの立場を明確にし、最も強い論拠を1つ示してください。\n\n"
            "【指示】\n"
            "- あなたの生活実感・専門知識に基づいた具体的な主張をしてください。\n"
            "- 「一般的に〜と言われている」のような他人事の論調は禁止。あなた自身の言葉で語ってください。\n"
            "- 可能なら、数字・実例・体験談を1つ以上含めてください。\n"
            "- argument は300文字以上で、自然な段落として書いてください。"
        ),
        2: (
            f"テーマ「{theme}」について、前ラウンドの議論を踏まえて回答してください。\n\n"
            "【指示】\n"
            "1. 前ラウンドで最も反論したい主張を1つ選び、「addressed_to」にその参加者名を記入し、具体的に反論してください。\n"
            "2. 他の参加者の主張で説得力があった点を1つ認めてください（誰のどの部分か明記）。\n"
            "3. あなたの立場が変わった場合は「belief_update」に正直に理由を記載してください。変わらなければ空文字で。\n"
            "4. argument は必ず300文字以上。反論の根拠を具体的に述べてください。"
        ),
        3: (
            f"テーマ「{theme}」について、これまでの2ラウンドの議論を踏まえた最終的な立場を述べてください。\n\n"
            "【指示】\n"
            "1. 初期の立場から変わった場合は「belief_update」にその理由を明記してください。\n"
            "2. 残っている懸念や未解決の論点を挙げてください。\n"
            "3. 他の参加者の主張で最も影響を受けたものを述べてください（誰のどの発言か）。\n"
            "4. この議論を通じて得た最も重要な気づきを1つ述べてください。\n"
            "5. argument は300文字以上で、あなたの最終見解を包括的にまとめてください。"
        ),
    }

    calls = []
    for p in participants:
        system_prompt = _build_meeting_system_prompt(p, theme, round_name)
        user_prompt = round_instructions.get(
            round_number,
            f"テーマ「{theme}」について、あなたの立場から議論してください。",
        )
        if prev_summary:
            user_prompt += f"\n\n{prev_summary}"

        calls.append({
            "provider": p["agent_profile"].get("llm_backend", "openai"),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": 0.75,
            "max_tokens": 4096,
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
                "addressed_to": result.get("addressed_to", ""),
                "belief_update": result.get("belief_update", ""),
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
                "position": str(result)[:500] if result else "",
                "argument": str(result) if result else "",
                "evidence": "",
                "addressed_to": "",
                "belief_update": "",
                "concerns": [],
                "questions_to_others": [],
                "usage": usage,
            }
        arguments.append(arg)

    # ConversationLog に保存
    if session and simulation_id:
        round_logs: list[ConversationLog] = []
        for arg in arguments:
            # 自然言語テキストを構築
            content_parts = []
            position = arg.get("position", "")
            argument = arg.get("argument", "")
            evidence = arg.get("evidence", "")
            addressed_to = arg.get("addressed_to", "")
            belief_update = arg.get("belief_update", "")

            if addressed_to:
                content_parts.append(f"（{addressed_to}さんへの応答）")
            if position:
                content_parts.append(f"【立場】{position}")
            if argument:
                content_parts.append(argument)
            if evidence:
                content_parts.append(f"【根拠】{evidence}")
            if belief_update:
                content_parts.append(f"【信念の変化】{belief_update}")

            content_text = "\n".join(content_parts)

            round_logs.append(ConversationLog(
                simulation_id=simulation_id,
                phase="meeting",
                round_number=round_number,
                participant_name=arg.get("participant_name", ""),
                participant_role=arg.get("role", ""),
                participant_index=arg.get("participant_index", -1),
                content_text=content_text,
                content_json={k: v for k, v in arg.items() if k != "usage"},
                stance=arg.get("position", ""),
                stance_changed=bool(belief_update),
                addressed_to=addressed_to,
            ))

        await persist_conversation_logs(
            session,
            round_logs,
            context=f"meeting conversation logs (round={round_number})",
        )

    if simulation_id:
        # 個別発言をリアルタイムストリーム
        for arg in arguments:
            await sse_manager.publish(simulation_id, "meeting_dialogue", {
                "round": round_number,
                "round_name": round_name,
                "participant_name": arg.get("participant_name", ""),
                "participant_index": arg.get("participant_index", 0),
                "role": arg.get("role", ""),
                "position": arg.get("position", ""),
                "argument": arg.get("argument", ""),
                "evidence": arg.get("evidence", ""),
                "addressed_to": arg.get("addressed_to", ""),
                "belief_update": arg.get("belief_update", ""),
                "concerns": arg.get("concerns", []),
                "questions_to_others": arg.get("questions_to_others", []),
            })

        # ラウンド完了サマリー
        await sse_manager.publish(simulation_id, "meeting_round_completed", {
            "round": round_number,
            "round_name": round_name,
            "argument_count": len(arguments),
        })

    return arguments


async def _run_direct_exchanges(
    arguments: list[dict],
    participants: list[dict],
    theme: str,
    round_number: int,
    simulation_id: str | None = None,
    session: Any = None,
) -> list[dict]:
    """モデレータが最も対立する2-3ペアを特定し、直接対話させる。

    Returns:
        追加の exchange 引数リスト（元の arguments には含まれない）
    """
    multi_llm_client.initialize()

    # モデレータ: 対立ペアを特定
    arg_summaries = "\n".join(
        f"- {a.get('participant_name', '?')}: {a.get('position', '')}。{(a.get('argument', '') or '')[:200]}"
        for a in arguments
    )

    moderator_system = (
        "あなたは議論のモデレーターです。参加者の主張を読んで、最も対立が深い・議論が面白い2組のペアを選んでください。\n"
        "各ペアは直接対話して論点を深掘りすべきです。\n\n"
        "出力はJSON形式のみ:\n"
        '{"pairs": [{"participant_a": "名前A", "participant_b": "名前B", "tension_topic": "対立の論点"}]}'
    )
    moderator_user = f"テーマ: {theme}\n\n参加者の主張:\n{arg_summaries}"

    try:
        mod_result, _ = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=moderator_system,
            user_prompt=moderator_user,
            temperature=0.3,
            max_tokens=1024,
        )
    except Exception as e:
        logger.warning("Moderator call failed, skipping direct exchanges: %s", e)
        return []

    pairs = []
    if isinstance(mod_result, dict):
        pairs = mod_result.get("pairs", [])[:2]

    if not pairs:
        return []

    # 名前→引数のマップ
    name_to_arg = {a.get("participant_name", ""): a for a in arguments}
    name_to_participant = {
        p.get("display_name", ""): p for p in participants
    }

    exchanges = []
    exchange_logs: list[ConversationLog] = []
    for pair in pairs:
        name_a = pair.get("participant_a", "")
        name_b = pair.get("participant_b", "")
        tension = pair.get("tension_topic", "")

        arg_a = name_to_arg.get(name_a)
        arg_b = name_to_arg.get(name_b)
        if not arg_a or not arg_b:
            continue

        part_a = name_to_participant.get(name_a)
        part_b = name_to_participant.get(name_b)
        if not part_a or not part_b:
            continue

        # A が B に応答
        exchange_system_a = _build_meeting_system_prompt(part_a, theme, f"直接対話（{tension}）")
        exchange_user_a = (
            f"{name_b}さんの主張:\n「{arg_b.get('argument', '')}」\n\n"
            f"論点: {tension}\n\n"
            f"この主張に対して直接応答してください。同意できる部分と反論すべき部分を明確にしてください。\n"
            f"300文字以上で、具体的に応答してください。"
        )

        # B が A に応答
        exchange_system_b = _build_meeting_system_prompt(part_b, theme, f"直接対話（{tension}）")
        exchange_user_b = (
            f"{name_a}さんの主張:\n「{arg_a.get('argument', '')}」\n\n"
            f"論点: {tension}\n\n"
            f"この主張に対して直接応答してください。同意できる部分と反論すべき部分を明確にしてください。\n"
            f"300文字以上で、具体的に応答してください。"
        )

        calls = [
            {
                "provider": part_a.get("agent_profile", {}).get("llm_backend", "openai"),
                "system_prompt": exchange_system_a,
                "user_prompt": exchange_user_a,
                "temperature": 0.75,
                "max_tokens": 2048,
            },
            {
                "provider": part_b.get("agent_profile", {}).get("llm_backend", "openai"),
                "system_prompt": exchange_system_b,
                "user_prompt": exchange_user_b,
                "temperature": 0.75,
                "max_tokens": 2048,
            },
        ]

        results = await multi_llm_client.call_batch_by_provider(calls, max_concurrency=2)

        for idx, (result, usage) in enumerate(results):
            responder = name_a if idx == 0 else name_b
            addressed = name_b if idx == 0 else name_a
            resp_participant = part_a if idx == 0 else part_b

            if isinstance(result, dict):
                argument_text = result.get("argument", "")
                position = result.get("position", "")
                belief_update = result.get("belief_update", "")
            else:
                argument_text = str(result) if result else ""
                position = ""
                belief_update = ""

            exchange_arg = {
                "participant_index": resp_participant.get("agent_profile", {}).get("agent_index", -1),
                "participant_name": responder,
                "role": resp_participant.get("role", ""),
                "expertise": resp_participant.get("expertise", ""),
                "round": round_number,
                "sub_round": "direct_exchange",
                "position": position,
                "argument": argument_text,
                "evidence": result.get("evidence", "") if isinstance(result, dict) else "",
                "addressed_to": addressed,
                "belief_update": belief_update,
                "tension_topic": tension,
                "concerns": result.get("concerns", []) if isinstance(result, dict) else [],
                "questions_to_others": result.get("questions_to_others", []) if isinstance(result, dict) else [],
                "usage": usage,
            }
            exchanges.append(exchange_arg)

            # SSE で直接対話をストリーム
            if simulation_id:
                await sse_manager.publish(simulation_id, "meeting_dialogue", {
                    "round": round_number,
                    "round_name": f"直接対話: {tension}",
                    "participant_name": responder,
                    "role": resp_participant.get("role", ""),
                    "position": position,
                    "argument": argument_text,
                    "addressed_to": addressed,
                    "belief_update": belief_update,
                    "tension_topic": tension,
                })

            # ConversationLog に保存
            if session and simulation_id:
                content_parts = [f"（{addressed}さんへの直接応答 — 論点: {tension}）"]
                if position:
                    content_parts.append(f"【立場】{position}")
                if argument_text:
                    content_parts.append(argument_text)
                if belief_update:
                    content_parts.append(f"【信念の変化】{belief_update}")

                exchange_logs.append(ConversationLog(
                    simulation_id=simulation_id,
                    phase="meeting",
                    round_number=round_number,
                    participant_name=responder,
                    participant_role=resp_participant.get("role", ""),
                    participant_index=resp_participant.get("agent_profile", {}).get("agent_index", -1),
                    content_text="\n".join(content_parts),
                    content_json=exchange_arg,
                    stance=position,
                    stance_changed=bool(belief_update),
                    addressed_to=addressed,
                ))

    if session and exchange_logs:
        await persist_conversation_logs(
            session,
            exchange_logs,
            context=f"meeting exchange logs (round={round_number})",
        )

    logger.info("Direct exchanges completed: %d exchanges from %d pairs", len(exchanges), len(pairs))
    return exchanges


async def _run_synthesis(
    all_arguments: list[list[dict]],
    theme: str,
    participants: list[dict],
) -> tuple[dict, dict]:
    """議論の総括を生成する。"""
    multi_llm_client.initialize()

    # ラウンド構造を保持して議論をまとめる
    round_names_map = {1: "初期主張", 2: "相互質疑・反論", 3: "最終立場表明"}
    discussion_parts = []
    for round_idx, round_args in enumerate(all_arguments):
        round_num = round_idx + 1
        round_label = round_names_map.get(round_num, f"ラウンド{round_num}")
        discussion_parts.append(f"=== {round_label}（ラウンド{round_num}） ===")
        for arg in round_args:
            name = arg.get("participant_name", "参加者")
            role = arg.get("role", "")
            position = arg.get("position", "")
            argument = arg.get("argument", "")
            evidence = arg.get("evidence", "")
            questions = arg.get("questions_to_others", [])
            parts = [f"[{name} ({role})] 立場: {position}", f"  主張: {argument}"]
            if evidence:
                parts.append(f"  根拠: {evidence}")
            if questions:
                parts.append(f"  他者への質問: {', '.join(questions[:2])}")
            discussion_parts.append("\n".join(parts))
        discussion_parts.append("")
    discussion_text = "\n\n".join(discussion_parts)

    system_prompt = (
        "あなたは会議のファシリテーターです。3ラウンドにわたる議論を総括してください。\n\n"
        "特に以下に注目して分析してください:\n"
        "1. ラウンド間で参加者のスタンスがどう変化したか\n"
        "2. どの論点が最も議論を動かしたか\n"
        "3. 合意に至った点と、依然として対立している点\n"
        "4. 今後の意思決定に有用なシナリオ\n\n"
        "出力は必ず以下のJSON形式のみで（JSON以外のテキスト不要）:\n"
        "{\n"
        '  "consensus_points": ["合意点1", "合意点2", ...],\n'
        '  "disagreement_points": [{"topic": "対立点", "positions": [{"participant": "名前", "position": "立場"}]}],\n'
        '  "key_insights": ["洞察1", "洞察2", ...],\n'
        '  "scenarios": [{"name": "シナリオ名", "description": "説明", "probability": 0.0-1.0, "key_factors": ["要因"]}],\n'
        '  "stance_shifts": [{"participant": "名前", "from": "変化前", "to": "変化後", "reason": "理由"}],\n'
        '  "most_persuasive_argument": {"participant": "名前", "argument": "最も影響力のあった主張"},\n'
        '  "recommendations": ["提言1", "提言2", ...],\n'
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
    session: Any = None,
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
            previous, simulation_id, session=session,
        )

        for arg in arguments:
            u = arg.get("usage", {})
            total_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += u.get("completion_tokens", 0)
            total_usage["total_tokens"] += u.get("total_tokens", 0)

        # ラウンド1, 2の後に直接対話サブラウンドを実行
        if round_idx + 1 < min(num_rounds, len(round_names)):  # 最終ラウンドでは不要
            try:
                exchanges = await _run_direct_exchanges(
                    arguments, participants, theme,
                    round_number=round_idx + 1,
                    simulation_id=simulation_id,
                    session=session,
                )
                if exchanges:
                    arguments.extend(exchanges)
                    for ex in exchanges:
                        u = ex.get("usage", {})
                        total_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
                        total_usage["completion_tokens"] += u.get("completion_tokens", 0)
                        total_usage["total_tokens"] += u.get("total_tokens", 0)
            except Exception as e:
                logger.warning("Direct exchanges failed, continuing: %s", e)

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
            "stance_shifts": synthesis.get("stance_shifts", []) if synthesis else [],
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
