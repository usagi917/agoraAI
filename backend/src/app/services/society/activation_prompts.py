"""活性化レイヤー用プロンプトテンプレート"""


def build_activation_prompt(agent: dict, theme: str) -> tuple[str, str]:
    """住民プロフィールとテーマからプロンプトを構築する。

    Returns:
        (system_prompt, user_prompt) のタプル
    """
    demographics = agent.get("demographics", {})
    big_five = agent.get("big_five", {})
    values = agent.get("values", {})

    # パーソナリティ記述
    personality_parts = []
    if big_five.get("O", 0.5) > 0.7:
        personality_parts.append("新しいアイデアに開放的")
    elif big_five.get("O", 0.5) < 0.3:
        personality_parts.append("伝統的な考えを好む")
    if big_five.get("E", 0.5) > 0.7:
        personality_parts.append("社交的で積極的")
    elif big_five.get("E", 0.5) < 0.3:
        personality_parts.append("内向的で慎重")
    if big_five.get("A", 0.5) > 0.7:
        personality_parts.append("協調的")
    elif big_five.get("A", 0.5) < 0.3:
        personality_parts.append("独立心が強い")
    if big_five.get("N", 0.5) > 0.7:
        personality_parts.append("不安を感じやすい")

    personality = "、".join(personality_parts) if personality_parts else "バランスの取れた性格"

    # 価値観記述
    top_values = sorted(values.items(), key=lambda x: x[1], reverse=True)[:3]
    value_str = "、".join(v[0] for v in top_values) if top_values else "特になし"

    # 生活コンテキスト
    life_event = agent.get("life_event", "")
    life_context = f"\n最近の出来事: {life_event}" if life_event else ""

    system_prompt = f"""あなたは以下のプロフィールを持つ日本の住民です。このプロフィールに基づいて、提示されたテーマについて率直な意見を述べてください。

【プロフィール】
- 年齢: {demographics.get('age', '不明')}歳
- 性別: {demographics.get('gender', '不明')}
- 職業: {demographics.get('occupation', '不明')}
- 地域: {demographics.get('region', '不明')}
- 学歴: {demographics.get('education', '不明')}
- 収入層: {demographics.get('income_bracket', '不明')}
- 性格: {personality}
- 重視する価値観: {value_str}
- 情報源: {agent.get('information_source', '不明')}
- 発話スタイル: {agent.get('speech_style', '自然')}
{life_context}

【指示】
以下の JSON 形式で回答してください:
{{
  "stance": "賛成" | "反対" | "中立" | "条件付き賛成" | "条件付き反対",
  "confidence": 0.0〜1.0の数値,
  "reason": "50〜150文字の理由",
  "concern": "最も気になる点（30文字以内）",
  "priority": "この問題で最も重視すること（30文字以内）"
}}"""

    user_prompt = f"テーマ: {theme}\n\nこのテーマについて、あなたの立場から意見を述べてください。"

    return system_prompt, user_prompt
