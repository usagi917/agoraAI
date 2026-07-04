"""Meeting prompt builders."""

from src.app.services.society.activation_prompts import SPEECH_STYLE_DIRECTIVES


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

    anti_consensus = (
        "\n\n【反合意ルール】\n"
        "あなたは簡単には意見を変えない人間である。以下の条件のうち2つ以上が満たされない限り、初期スタンスを維持せよ：\n"
        "（a）自分が知らなかった具体的な事実を突きつけられた\n"
        "（b）自分の生活に直接影響する新しい視点を示された\n"
        "（c）反論の根拠が自分の経験と矛盾しない\n"
        "議論の最後に全員が同意するのは非現実的である。あなたの最終立場は、あなたの生活実感に基づくものでなければならない。"
    )

    return (
        f"あなたは以下のプロフィールを持つ市民代表として議論に参加しています。\n\n"
        f"{context}\n\n"
        f"テーマ: {theme}\n\n"
        f"議論フェーズ: {round_name}\n\n"
        f"【最重要ルール】あなたのプロフィール・年齢・職業・話し方ルールに基づいて、"
        f"あなたという人間がそのまま喋っているように議論せよ。"
        f"全員が同じような敬語で話すのは不自然。あなたのキャラクターを貫け。"
        f"他の参加者と同じ語彙・文体で話してはならない。あなた固有の言い回しを使え。"
        f"{anti_consensus}"
        f"{devil_advocate_instruction}"
        f"{opposing_block}"
        f"{belief_update_instruction}\n\n"
        f"{json_format}"
    )
