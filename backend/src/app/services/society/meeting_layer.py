"""Meeting Layer: 代表者+専門家による多ラウンド構造化議論"""

import logging
from typing import Any

from src.app.llm.multi_client import multi_llm_client
from src.app.models.conversation_log import ConversationLog
from src.app.services.conversation_log_store import persist_conversation_logs
from src.app.services.society.activation_layer import _temperature_from_big_five
from src.app.services.society.activation_prompts import SPEECH_STYLE_DIRECTIVES
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

# Meeting はフルBDIの代わりに、軽量な構造化議論プロトコルを使用
# Phase 2 では debate_protocol の3フェーズ構造を再現する

MEETING_ROUNDS = 3  # Claims → Counters → Synthesis


def _resolve_participant_index(participant: dict, fallback: int = -1) -> int:
    """参加者の実エージェント index を返す。"""
    agent_profile = participant.get("agent_profile", {}) or {}
    participant_index = agent_profile.get("agent_index")
    return participant_index if isinstance(participant_index, int) else fallback


def _normalize_participant_name(name: str) -> str:
    return " ".join(str(name).split()).strip()


def _match_participant_index_by_name(name: str, participants: list[dict]) -> int | None:
    """参加者名から agent_index を逆引きする。"""
    normalized = _normalize_participant_name(name)
    if not normalized:
        return None

    for participant in participants:
        display_name = _normalize_participant_name(participant.get("display_name", ""))
        if not display_name:
            continue
        if normalized == display_name or normalized in display_name or display_name in normalized:
            return _resolve_participant_index(participant, -1)
    return None


def _serialize_argument_for_stream(arg: dict, round_name: str) -> dict[str, Any]:
    """SSE 用に発言データを整形する。"""
    return {
        "round": arg.get("round", 0),
        "round_name": round_name,
        "participant_name": arg.get("participant_name", ""),
        "participant_index": arg.get("participant_index", -1),
        "role": arg.get("role", ""),
        "expertise": arg.get("expertise", ""),
        "position": arg.get("position", ""),
        "argument": arg.get("argument", ""),
        "evidence": arg.get("evidence", ""),
        "addressed_to": arg.get("addressed_to", ""),
        "addressed_to_participant_index": arg.get("addressed_to_participant_index"),
        "belief_update": arg.get("belief_update", ""),
        "concerns": arg.get("concerns", []),
        "questions_to_others": arg.get("questions_to_others", []),
        "is_devil_advocate": bool(arg.get("is_devil_advocate", False)),
        "sub_round": arg.get("sub_round", ""),
        "tension_topic": arg.get("tension_topic", ""),
    }


def enrich_meeting_with_clusters(
    participants: list[dict],
    clusters: list[Any] | None,
    activation_responses: list[dict],
) -> list[dict]:
    """Assign opposing cluster arguments to meeting participants.

    For each participant, finds which cluster they belong to, then collects
    the top 3 strongest arguments (by confidence) from opposing cluster(s).
    Devil's advocates receive arguments from ALL clusters they're NOT in.

    Args:
        participants: Meeting participant dicts with agent_profile.
        clusters: List of ClusterInfo from network propagation. If empty/None,
            returns participants unchanged.
        activation_responses: Activation layer responses with agent_id, stance,
            confidence, reason.

    Returns:
        participants list with ``opposing_arguments`` added to each dict.
    """
    if not clusters:
        for p in participants:
            p.setdefault("opposing_arguments", [])
        return participants

    # Build response lookup by agent_id
    resp_by_id: dict[str, dict] = {}
    for r in activation_responses:
        resp_by_id[r["agent_id"]] = r

    # Build agent_id -> cluster label mapping
    agent_cluster: dict[str, int] = {}
    for cluster in clusters:
        for member_id in cluster.member_ids:
            agent_cluster[member_id] = cluster.label

    # Build cluster label -> list of responses mapping
    cluster_responses: dict[int, list[dict]] = {}
    for cluster in clusters:
        resps = []
        for member_id in cluster.member_ids:
            resp = resp_by_id.get(member_id)
            if resp:
                resps.append(resp)
        cluster_responses[cluster.label] = resps

    all_cluster_labels = {c.label for c in clusters}

    for p in participants:
        agent_profile = p.get("agent_profile", {}) or {}
        agent_id = agent_profile.get("id", "")
        is_devil = p.get("is_devil_advocate", False)

        my_cluster = agent_cluster.get(agent_id)

        # Determine which clusters to draw arguments from
        if my_cluster is not None:
            opposing_labels = all_cluster_labels - {my_cluster}
        else:
            # Agent not in any cluster: use all clusters
            opposing_labels = all_cluster_labels

        # For non-devil advocates, limit to opposing clusters
        # For devil's advocates, already using all non-own clusters (same logic)
        opposing_args: list[dict] = []
        for label in opposing_labels:
            for resp in cluster_responses.get(label, []):
                reason = resp.get("reason", "")
                if reason:
                    opposing_args.append({
                        "reason": reason,
                        "confidence": resp.get("confidence", 0.5),
                        "stance": resp.get("stance", "中立"),
                        "agent_id": resp.get("agent_id", ""),
                    })

        # Sort by confidence descending, take top 3
        opposing_args.sort(key=lambda x: x["confidence"], reverse=True)
        p["opposing_arguments"] = opposing_args[:3]

    return participants


def _build_balanced_briefing(theme: str, grounding_facts: list[dict] | None = None) -> str:
    """テーマに関するバランスの取れたブリーフィングを生成する（テンプレートベース、LLM不要）。"""
    facts_section = ""
    if grounding_facts:
        facts_lines = "\n".join(f"・{f['fact']}（{f['source']}）" for f in grounding_facts[:5])
        facts_section = f"\n【関連データ】\n{facts_lines}\n"

    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"【議論の前提情報】テーマ: {theme}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{facts_section}\n"
        f"このテーマについて、以下のような賛否の論点が存在します:\n\n"
        f"【賛成側の主な論点】\n"
        f"・経済的便益や効率性の向上が期待できる\n"
        f"・国際的な競争力や先行事例との整合性\n"
        f"・長期的な社会課題の解決に寄与する可能性\n\n"
        f"【反対側の主な論点】\n"
        f"・短期的なコストや負担増への懸念\n"
        f"・地域格差や社会的弱者への影響\n"
        f"・実施の実現可能性や副作用のリスク\n\n"
        f"上記を踏まえた上で、あなた自身の立場から議論してください。\n"
    )


def _build_speech_style_block(speech_style: str) -> str:
    """speech_style指示ブロックを構築する。"""
    style = SPEECH_STYLE_DIRECTIVES.get(speech_style, {})
    if not style:
        return f"話し方: {speech_style}"
    return (
        f"【話し方ルール: {speech_style}】\n"
        f"{style['instruction']}\n"
        f"参考: 「{style['example']}」\n"
        f"禁止: {style['prohibition']}"
    )


def _build_participant_context(participant: dict) -> str:
    """参加者のコンテキスト文字列を構築する。"""
    if participant["role"] == "expert":
        persona = participant.get("persona", {})
        # エキスパート固有の性格情報を含める
        context_parts = [
            f"【{participant.get('display_name', '専門家')}】",
            f"役割: {persona.get('role', '')}",
            f"焦点: {persona.get('focus', '')}",
            f"思考スタイル: {persona.get('thinking_style', '')}",
        ]
        if persona.get("intellectual_biases"):
            context_parts.append(f"あなたの思考傾向（自覚なし）: {'; '.join(persona['intellectual_biases'])}")
        if persona.get("blind_spots"):
            context_parts.append(f"あなたが見落としがちな点: {'; '.join(persona['blind_spots'])}")
        if persona.get("rhetorical_style"):
            context_parts.append(f"話し方の癖: {persona['rhetorical_style']}")
        if persona.get("hot_buttons"):
            context_parts.append(f"つい熱くなるテーマ: {'; '.join(persona['hot_buttons'])}")
        return "\n".join(context_parts)

    agent = participant["agent_profile"]
    demo = agent.get("demographics", {})
    resp = participant.get("response", {}) or {}
    concern = resp.get("concern", "")
    priority = resp.get("priority", "")
    speech_style = agent.get("speech_style", "自然")

    extra_parts = []
    if concern:
        extra_parts.append(f"最大の懸念: {concern}")
    if priority:
        extra_parts.append(f"重視すること: {priority}")
    # 生活文脈を追加
    persona_narrative = agent.get("persona_narrative", "")
    if persona_narrative:
        extra_parts.append(f"あなたの背景: {persona_narrative[:200]}")
    contradiction = agent.get("contradiction", "")
    if contradiction:
        extra_parts.append(f"内面の葛藤: {contradiction}")
    hidden_motivation = agent.get("hidden_motivation", "")
    if hidden_motivation:
        extra_parts.append(f"本音（表には出さないが行動に影響）: {hidden_motivation}")

    extra_text = "\n".join(extra_parts)

    speech_block = _build_speech_style_block(speech_style)

    return (
        f"【市民代表: {demo.get('occupation', '不明')}・{demo.get('age', '?')}歳・{demo.get('region', '不明')}】\n"
        f"スタンス: {resp.get('stance', '中立')} (信頼度: {resp.get('confidence', 0.5):.1%})\n"
        f"理由: {resp.get('reason', '')}\n"
        f"{extra_text}\n\n"
        f"{speech_block}"
    )


def _build_meeting_system_prompt(participant: dict, theme: str, round_name: str) -> str:
    """Meeting 用のシステムプロンプトを構築する。

    2フェーズ方式:
    - Phase 1 (voice): 自然言語で発話（speech_styleを厳守）
    - Phase 2 (extraction): 別途JSON抽出（この関数では voice を要求）

    出力はJSON形式だが、argument フィールドは完全に自然言語。
    """
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
        '  "argument": "300-600文字の主張。【重要】あなたの話し方ルールに厳密に従い、'
        "あなたという人間がそのまま喋っているように書け。"
        "22歳のフリーターと65歳の元官僚では言葉遣いが全く違うはず。"
        "経験・知識に基づく具体的な論拠を含め、あなたの口調・語彙・リズムで語れ。"
        '抽象的な一般論は禁止。",\n'
        '  "evidence": "根拠となる事実・データ・実体験（簡潔に）",\n'
        '  "addressed_to": "応答先の参加者名（ラウンド2以降。ラウンド1は空文字）",\n'
        '  "belief_update": "前ラウンドから立場が変わった場合、何に説得されたか（変化なしなら空文字）",\n'
        '  "concerns": ["懸念事項"],\n'
        '  "questions_to_others": ["他の参加者への具体的な質問"]\n'
        "}"
    )

    if participant["role"] == "expert":
        persona = participant.get("persona", {})
        prompts = participant.get("prompts", {})
        expert_instruction = prompts.get("analyze", "専門的知見に基づいて分析してください。")

        # エキスパート固有のキャラクター指示
        character_parts = []
        if persona.get("rhetorical_style"):
            character_parts.append(f"あなたの話し方の癖: {persona['rhetorical_style']}")
        if persona.get("intellectual_biases"):
            character_parts.append(
                "あなたは以下の思考傾向を持っている（自覚なし。自然にこの傾向が発言に表れる）:\n"
                + "\n".join(f"- {b}" for b in persona["intellectual_biases"])
            )
        if persona.get("hot_buttons"):
            character_parts.append(
                "以下のテーマに触れると、つい感情が出て普段より強い主張をしてしまう:\n"
                + "\n".join(f"- {h}" for h in persona["hot_buttons"])
            )
        character_block = "\n\n".join(character_parts) if character_parts else ""

        return (
            f"あなたは以下の専門家として議論に参加しています。\n\n"
            f"{context}\n\n"
            f"テーマ: {theme}\n\n"
            f"議論フェーズ: {round_name}\n\n"
            f"専門家としての指示:\n{expert_instruction}\n\n"
            f"{character_block}"
            f"{devil_advocate_instruction}\n\n"
            f"【重要】argument は、あなたという専門家が会議室で実際に発言しているように書け。"
            f"論文の要旨ではなく、生きた人間の発言として。口癖や思考傾向を自然に反映させよ。\n\n"
            f"{json_format}"
        )

    # 市民代表の場合
    belief_update_instruction = (
        "\n\n【信念更新について】他の参加者の主張に説得力を感じた場合、立場を変えてもよい。"
        "ただし簡単に変えすぎないこと。あなたには生活実感に基づく確信がある。"
        "変える場合は「何が」「なぜ」あなたを動かしたのかを具体的に書け。"
    )

    # Opposing cluster arguments (from enrich_meeting_with_clusters)
    opposing_args = participant.get("opposing_arguments", [])
    opposing_block = ""
    if opposing_args:
        arg_lines = "\n".join(
            f"- 「{a['reason']}」（{a.get('stance', '不明')}）"
            for a in opposing_args
            if a.get("reason")
        )
        if arg_lines:
            opposing_block = (
                "\n\n以下は対立するグループからの最も強い主張です：\n"
                f"{arg_lines}\n"
                "これらの主張を踏まえた上で、自分の立場を明確にしてください。"
            )

    return (
        f"あなたは以下のプロフィールを持つ市民代表として議論に参加しています。\n\n"
        f"{context}\n\n"
        f"テーマ: {theme}\n\n"
        f"議論フェーズ: {round_name}\n\n"
        f"【最重要ルール】あなたのプロフィール・年齢・職業・話し方ルールに基づいて、"
        f"あなたという人間がそのまま喋っているように議論せよ。"
        f"全員が同じような敬語で話すのは不自然。あなたのキャラクターを貫け。"
        f"{devil_advocate_instruction}"
        f"{opposing_block}"
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
    briefing_prefix: str = "",
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
        if briefing_prefix and round_number == 1:
            user_prompt = briefing_prefix + "\n\n" + user_prompt
        if prev_summary:
            user_prompt += f"\n\n{prev_summary}"

        agent_temperature = _temperature_from_big_five(
            p["agent_profile"].get("big_five", {}), base_temperature=0.75,
        )
        calls.append({
            "provider": p["agent_profile"].get("llm_backend", "openai"),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": agent_temperature,
            "max_tokens": 4096,
        })

    results = await multi_llm_client.call_batch_by_provider(calls, max_concurrency=10)

    arguments = []
    for i, (result, usage) in enumerate(results):
        p = participants[i]
        name = p.get("display_name", "") or p["agent_profile"].get("demographics", {}).get("occupation", f"参加者{i+1}")
        participant_index = _resolve_participant_index(p, i)
        is_devil_advocate = bool(p.get("is_devil_advocate", False))
        addressed_to = result.get("addressed_to", "") if isinstance(result, dict) else ""
        addressed_to_participant_index = _match_participant_index_by_name(addressed_to, participants)

        if isinstance(result, dict):
            arg = {
                "participant_index": participant_index,
                "participant_name": name,
                "role": p["role"],
                "expertise": p.get("expertise", ""),
                "round": round_number,
                "position": result.get("position", ""),
                "argument": result.get("argument", ""),
                "evidence": result.get("evidence", ""),
                "addressed_to": addressed_to,
                "addressed_to_participant_index": addressed_to_participant_index,
                "belief_update": result.get("belief_update", ""),
                "concerns": result.get("concerns", []),
                "questions_to_others": result.get("questions_to_others", []),
                "is_devil_advocate": is_devil_advocate,
                "usage": usage,
            }
        else:
            arg = {
                "participant_index": participant_index,
                "participant_name": name,
                "role": p["role"],
                "expertise": p.get("expertise", ""),
                "round": round_number,
                "position": str(result)[:500] if result else "",
                "argument": str(result) if result else "",
                "evidence": "",
                "addressed_to": addressed_to,
                "addressed_to_participant_index": addressed_to_participant_index,
                "belief_update": "",
                "concerns": [],
                "questions_to_others": [],
                "is_devil_advocate": is_devil_advocate,
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
            await sse_manager.publish(
                simulation_id,
                "meeting_dialogue",
                _serialize_argument_for_stream(arg, round_name),
            )

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

        temp_a = _temperature_from_big_five(
            part_a.get("agent_profile", {}).get("big_five", {}), base_temperature=0.75,
        )
        temp_b = _temperature_from_big_five(
            part_b.get("agent_profile", {}).get("big_five", {}), base_temperature=0.75,
        )
        calls = [
            {
                "provider": part_a.get("agent_profile", {}).get("llm_backend", "openai"),
                "system_prompt": exchange_system_a,
                "user_prompt": exchange_user_a,
                "temperature": temp_a,
                "max_tokens": 2048,
            },
            {
                "provider": part_b.get("agent_profile", {}).get("llm_backend", "openai"),
                "system_prompt": exchange_system_b,
                "user_prompt": exchange_user_b,
                "temperature": temp_b,
                "max_tokens": 2048,
            },
        ]

        results = await multi_llm_client.call_batch_by_provider(calls, max_concurrency=2)

        for idx, (result, usage) in enumerate(results):
            responder = name_a if idx == 0 else name_b
            addressed = name_b if idx == 0 else name_a
            resp_participant = part_a if idx == 0 else part_b
            participant_index = _resolve_participant_index(resp_participant, -1)
            addressed_to_participant_index = _resolve_participant_index(part_b if idx == 0 else part_a, -1)

            if isinstance(result, dict):
                argument_text = result.get("argument", "")
                position = result.get("position", "")
                belief_update = result.get("belief_update", "")
            else:
                argument_text = str(result) if result else ""
                position = ""
                belief_update = ""

            exchange_arg = {
                "participant_index": participant_index,
                "participant_name": responder,
                "role": resp_participant.get("role", ""),
                "expertise": resp_participant.get("expertise", ""),
                "round": round_number,
                "sub_round": "direct_exchange",
                "position": position,
                "argument": argument_text,
                "evidence": result.get("evidence", "") if isinstance(result, dict) else "",
                "addressed_to": addressed,
                "addressed_to_participant_index": addressed_to_participant_index,
                "belief_update": belief_update,
                "tension_topic": tension,
                "concerns": result.get("concerns", []) if isinstance(result, dict) else [],
                "questions_to_others": result.get("questions_to_others", []) if isinstance(result, dict) else [],
                "is_devil_advocate": bool(resp_participant.get("is_devil_advocate", False)),
                "usage": usage,
            }
            exchanges.append(exchange_arg)

            # SSE で直接対話をストリーム
            if simulation_id:
                await sse_manager.publish(
                    simulation_id,
                    "meeting_dialogue",
                    _serialize_argument_for_stream(exchange_arg, f"直接対話: {tension}"),
                )

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

    # バランスド・ブリーフィングを生成（Fishkin 熟議民主主義）
    grounding_facts: list[dict] = []
    for p in participants:
        profile = p.get("agent_profile", {}) or {}
        facts = profile.get("grounding_facts", [])
        if isinstance(facts, list):
            grounding_facts.extend(facts)
    balanced_briefing = _build_balanced_briefing(theme, grounding_facts if grounding_facts else None)

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
            briefing_prefix=balanced_briefing if round_idx == 0 else "",
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

        if simulation_id:
            await sse_manager.publish(simulation_id, "meeting_round_completed", {
                "round": round_idx + 1,
                "round_name": round_name,
                "argument_count": len(arguments),
                "arguments": [
                    _serialize_argument_for_stream(arg, round_name)
                    for arg in arguments
                ],
            })

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
        "balanced_briefing": balanced_briefing,
    }
