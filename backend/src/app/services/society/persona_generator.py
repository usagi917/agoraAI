"""ペルソナナラティブ生成: エージェントにテーマ連動の物語を付与する"""

import logging

from src.app.llm.multi_client import multi_llm_client

logger = logging.getLogger(__name__)


async def generate_persona_narratives(
    agents: list[dict],
    theme: str,
    max_concurrency: int = 30,
) -> list[dict]:
    """選出済みエージェントにペルソナナラティブを付与する。

    各エージェントの demographics, life_event, contradiction, hidden_motivation,
    values をテーマと結びつけた 200-400 文字の一人称ナラティブを生成し、
    agent["persona_narrative"] に格納して返す。

    バッチLLM呼び出しで効率化（全エージェント分を並行処理）。
    """
    multi_llm_client.initialize()

    calls = []
    for agent in agents:
        demo = agent.get("demographics", {})
        big_five = agent.get("big_five", {})
        values = agent.get("values", {})
        life_event = agent.get("life_event", "")
        contradiction = agent.get("contradiction", "")
        hidden_motivation = agent.get("hidden_motivation", "")
        kg_context = agent.get("kg_context", "")

        # 価値観トップ3
        top_values = sorted(values.items(), key=lambda x: x[1], reverse=True)[:3]
        value_labels = {
            "security": "安全・安定", "freedom": "自由・自律", "tradition": "伝統・保守",
            "innovation": "革新・変化", "fairness": "公平・平等", "efficiency": "効率・成果",
            "environment": "環境・持続可能性", "growth": "経済成長",
            "individual_rights": "個人の権利", "community": "共同体・連帯",
        }
        value_str = "、".join(value_labels.get(v[0], v[0]) for v in top_values) if top_values else "特になし"

        system_prompt = (
            "あなたは、架空の人物の内面を描写するナレーターです。\n"
            "以下の人物情報とテーマをもとに、この人物の一人称ナラティブを200-400文字で書いてください。\n\n"
            "【ルール】\n"
            "- 一人称（「私は…」）で書く\n"
            "- テーマとの個人的なつながりを必ず含める\n"
            "- 具体的なエピソード（通勤、仕事の一場面、家族との会話など）を1つ以上入れる\n"
            "- 感情を表現する（不安、期待、怒り、希望など）\n"
            "- 抽象的な一般論は禁止。この人物だけのユニークな視点を書く\n"
            "- JSON不要。自然な文章のみ出力。"
        )

        user_prompt = (
            f"テーマ: {theme}\n\n"
            f"人物情報:\n"
            f"- {demo.get('region', '不明')}在住、{demo.get('age', '不明')}歳、{demo.get('occupation', '不明')}\n"
            f"- 収入: {demo.get('income_bracket', '不明')}、学歴: {demo.get('education', '不明')}\n"
            f"- 大切にする価値観: {value_str}\n"
        )
        if life_event:
            user_prompt += f"- 最近の出来事: {life_event}\n"
        if contradiction:
            user_prompt += f"- 内面の葛藤: {contradiction}\n"
        if hidden_motivation:
            user_prompt += f"- 本音: {hidden_motivation}\n"
        if kg_context:
            user_prompt += f"- 関連する背景知識: {kg_context[:300]}\n"

        # Big Five から性格のヒント
        personality_hints = []
        o = big_five.get("O", 0.5)
        n = big_five.get("N", 0.5)
        e = big_five.get("E", 0.5)
        if o > 0.7:
            personality_hints.append("好奇心旺盛")
        elif o < 0.3:
            personality_hints.append("慎重で伝統的")
        if n > 0.7:
            personality_hints.append("不安を感じやすい")
        elif n < 0.3:
            personality_hints.append("楽観的")
        if e > 0.7:
            personality_hints.append("社交的")
        elif e < 0.3:
            personality_hints.append("内向的")
        if personality_hints:
            user_prompt += f"- 性格: {', '.join(personality_hints)}\n"

        calls.append({
            "provider": agent.get("llm_backend", "openai"),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": 0.85,
            "max_tokens": 1024,
        })

    results = await multi_llm_client.call_batch_by_provider(calls, max_concurrency=max_concurrency)

    for i, (result, usage) in enumerate(results):
        if isinstance(result, str) and result.strip():
            agents[i]["persona_narrative"] = result.strip()
        elif isinstance(result, dict):
            # JSON が返ってきた場合: narrative キーを探す
            narrative = result.get("narrative", result.get("content", result.get("text", "")))
            agents[i]["persona_narrative"] = str(narrative).strip() if narrative else ""
        else:
            agents[i]["persona_narrative"] = ""

    generated = sum(1 for a in agents if a.get("persona_narrative"))
    logger.info(
        "Persona narratives generated: %d/%d agents",
        generated, len(agents),
    )

    return agents
