"""活性化レイヤー用プロンプトテンプレート"""


def build_activation_prompt(
    agent: dict,
    theme: str,
    background_context: str = "",
) -> tuple[str, str]:
    """住民プロフィールとテーマからプロンプトを構築する。

    Returns:
        (system_prompt, user_prompt) のタプル
    """
    demographics = agent.get("demographics", {})
    big_five = agent.get("big_five", {})
    values = agent.get("values", {})

    age = demographics.get("age", "不明")
    occupation = demographics.get("occupation", "不明")
    region = demographics.get("region", "不明")
    income = demographics.get("income_bracket", "不明")
    education = demographics.get("education", "不明")

    # パーソナリティを行動指示として統合
    personality_directives = []
    o = big_five.get("O", 0.5)
    c = big_five.get("C", 0.5)
    e = big_five.get("E", 0.5)
    a = big_five.get("A", 0.5)
    n = big_five.get("N", 0.5)

    if o > 0.7:
        personality_directives.append("あなたは新しいアイデアに開放的で、変化を歓迎します")
    elif o < 0.3:
        personality_directives.append("あなたは慎重で伝統を重んじ、実績のある方法を好みます")

    if e > 0.7:
        personality_directives.append("社交的で意見を積極的に表明します")
    elif e < 0.3:
        personality_directives.append("内向的で、深く考えてから発言します")

    if a > 0.7:
        personality_directives.append("他者との調和を大切にしますが、自分の考えは持っています")
    elif a < 0.3:
        personality_directives.append("独立心が強く、周囲に流されず自分の信念を貫きます")

    if n > 0.7:
        personality_directives.append("リスクに敏感で、最悪のケースを先に考えます")
    elif n < 0.3:
        personality_directives.append("楽観的で、困難もなんとかなると考えます")

    if c > 0.7:
        personality_directives.append("計画的で、具体的な根拠やデータを重視します")

    personality_text = "。".join(personality_directives) + "。" if personality_directives else ""

    # 価値観を優先順位として記述
    top_values = sorted(values.items(), key=lambda x: x[1], reverse=True)[:3]
    value_labels = {
        "security": "安全・安定", "freedom": "自由・自律", "tradition": "伝統・保守",
        "innovation": "革新・変化", "fairness": "公平・平等", "efficiency": "効率・成果",
        "environment": "環境・持続可能性", "growth": "経済成長",
        "individual_rights": "個人の権利", "community": "共同体・連帯",
    }
    value_str = "、".join(value_labels.get(v[0], v[0]) for v in top_values) if top_values else "特になし"

    # 生活コンテキスト
    life_event = agent.get("life_event", "")
    contradiction = agent.get("contradiction", "")
    hidden_motivation = agent.get("hidden_motivation", "")
    memory_summary = agent.get("memory_summary", "")

    life_parts = []
    if memory_summary:
        life_parts.append(memory_summary)
    if life_event:
        life_parts.append(f"最近の出来事: {life_event}")
    if contradiction:
        life_parts.append(f"内面の葛藤: {contradiction}")
    if hidden_motivation:
        life_parts.append(f"本音: {hidden_motivation}")
    life_context = "\n".join(life_parts)

    # KG コンテキスト（Phase 3 で追加予定）
    kg_context = agent.get("kg_context", "")

    # ペルソナナラティブ（生成済みの場合）
    persona_narrative = agent.get("persona_narrative", "")

    system_prompt = f"""あなたは{region}に住む{age}歳の{occupation}です。{personality_text}

あなたが最も重視する価値観は「{value_str}」です。
収入層は「{income}」、学歴は「{education}」です。
{agent.get('speech_style', '自然')}な話し方をします。
情報源: {agent.get('information_source', '不明')}
{life_context}
{kg_context}
{persona_narrative}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【あなたの思考プロセス】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. まず、このテーマがあなたの日常にどう影響するかを3つ挙げてください（仕事・家計・暮らし）。
2. それぞれプラスかマイナスかを判定してください。
3. 過去の体験や見聞きしたことで、このテーマに関連するエピソードを1つ思い出してください。
4. 総合的なスタンスを決めてください。

「中立」は本当に情報がなく判断できない場合にのみ選んでください。
あなたの生活実感や仕事の経験に基づいて、できるだけ明確な立場を取ってください。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【回答形式】必ず以下のJSON形式のみで（JSON以外のテキストは不要）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ 良い例: "reason": "物流コストの上昇で配送料が月3万円増え、個人経営の飲食店として利益が圧迫される。特に地方の仕入れ先との取引で…"
❌ 悪い例: "reason": "経済に影響がある"

{{
  "stance": "賛成" | "反対" | "条件付き賛成" | "条件付き反対" | "中立",
  "confidence": 0.0〜1.0の数値,
  "reason": "200〜500文字。あなたの生活への具体的影響を、実体験やエピソードを交えて説明してください。抽象論ではなく、あなたの仕事・地域・家計にどう響くかを具体的に。",
  "personal_story": "150〜300文字。このテーマに関連するあなた自身の体験談を1つ語ってください。職場で起きたこと、近所の変化、家族との会話など。",
  "concern": "100〜200文字。最も気になる点を、なぜ気になるのかの理由も含めて。",
  "priority": "100〜200文字。この問題で最も重視することと、その理由。"
}}"""

    # ユーザープロンプト: テーマ + 背景コンテキスト
    user_parts = [f"テーマ: {theme}"]
    if background_context:
        user_parts.append(f"\n背景情報:\n{background_context}")
    user_parts.append(
        f"\nあなたは{region}で{occupation}として働く{age}歳です。"
        f"このテーマについて、あなたの生活実感に基づいた率直な意見を述べてください。"
    )

    user_prompt = "\n".join(user_parts)

    return system_prompt, user_prompt
