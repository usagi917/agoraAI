"""非LLM人口のスタンス変化から、市民の声コメントを決定論的に生成する。"""

from __future__ import annotations

import random

from src.app.services.society.age_utils import age_bracket_5
from src.app.services.society.constants import STANCE_ORDER


_STANCE_PHRASES: dict[str, tuple[str, str, str, str]] = {
    "賛成": (
        "この案には賛成です", "これは進める価値があると思います", "私は支持します", "ぜひ実現してほしいです",
    ),
    "条件付き賛成": (
        "条件が整うなら賛成です", "課題への手当てがあれば支持できます", "進め方次第では賛成です", "必要な条件を満たすなら前向きです",
    ),
    "中立": (
        "今はまだ判断を保留したいです", "賛否どちらとも決めきれません", "もう少し材料を見たいです", "現時点では中立です",
    ),
    "条件付き反対": (
        "今の条件のままでは反対です", "懸念が解消されない限り支持できません", "修正がなければ反対します", "この進め方には慎重にならざるを得ません",
    ),
    "反対": (
        "この案には反対です", "これは受け入れられません", "進めるべきではないと思います", "私は明確に反対します",
    ),
}

# 導入と語尾を文体固有にすることで、同じスタンスでも声色が明確に変わる。
_STYLE_TONES: dict[str, tuple[str, str]] = {
    "率直で簡潔": ("正直、", "。"),
    "感情的で熱心": ("本当に大事なことだから言いますが、", "！みんなで真剣に考えてほしいです。"),
    "分析的で論理的": ("費用と効果を整理して考えると、", "。根拠と検証結果で判断すべきです。"),
    "控えめで消極的": ("私なんかが言うのも恐縮ですが、", "…という気がします。"),
    "攻撃的で主張が強い": ("はっきり言わせてもらうと、", "。曖昧なまま進めるのは許せません。"),
    "共感的で聞き上手": ("いろいろな立場の気持ちも分かります。そのうえで、", "。皆さんの声も丁寧に聞きたいです。"),
    "皮肉っぽい": ("また立派な話が出てきましたが、", "。現実もその看板どおりならいいですね。"),
    "楽観的": ("きっとうまく工夫できると思うので、", "。前向きにやってみましょう。"),
    "丁寧で慎重": ("慎重に申し上げると、", "。十分に確認しながら進めていただきたいです。"),
    "ユーモアを交える": ("難しい話で頭が湯気を出しそうですが、", "。笑って済ませず、ちゃんと考えたいですね。"),
}


def _build_base_templates(prefix: str, suffix: str, stance: str) -> tuple[str, ...]:
    phrases = _STANCE_PHRASES[stance]
    return tuple(
        f"{prefix}{{occupation}}としては、{phrase}{suffix}" if i % 2 == 0
        else f"{prefix}{{age}}歳の一市民として、{phrase}{suffix}"
        for i, phrase in enumerate(phrases)
    )


BASE_TEMPLATES: dict[str, dict[str, tuple[str, ...]]] = {
    style: {
        stance: _build_base_templates(prefix, suffix, stance)
        for stance in STANCE_ORDER
    }
    for style, (prefix, suffix) in _STYLE_TONES.items()
}

FALLBACK_TEMPLATES: dict[str, tuple[str, ...]] = {
    stance: tuple(
        f"{{occupation}}として考えると、{phrase}。" if i % 2 == 0
        else f"{{age}}歳の一市民として、{phrase}。"
        for i, phrase in enumerate(phrases)
    )
    for stance, phrases in _STANCE_PHRASES.items()
}

CHANGE_TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    style: {
        stance: (
            f"{prefix}以前は{{prev_stance}}でしたが、{{occupation}}として考え直し、{_STANCE_PHRASES[stance][0]}{suffix}",
            f"{prefix}{{prev_stance}}寄りだった考えが変わり、今は{_STANCE_PHRASES[stance][1]}{suffix}",
        )
        for stance in STANCE_ORDER
    }
    for style, (prefix, suffix) in _STYLE_TONES.items()
}

FALLBACK_CHANGE_TEMPLATES: dict[str, tuple[str, str]] = {
    stance: (
        f"以前は{{prev_stance}}でしたが、考え直して{phrases[0]}。",
        f"{{prev_stance}}寄りだった考えが変わり、今は{phrases[1]}。",
    )
    for stance, phrases in _STANCE_PHRASES.items()
}

_LIFE_EVENT_ADDITIONS = (
    "最近の「{life_event}」という経験からも、これは身近な問題です。",
    "「{life_event}」を経験した今だからこそ、そう感じます。",
    "私自身、{life_event}という出来事があり、この点は他人事ではありません。",
    "{life_event}をきっかけに、暮らしへの影響を以前より考えるようになりました。",
)


def _seed_value(seed: int | None, round_index: int) -> int:
    return (seed or 0) * 1_000_003 + round_index


def _comment(
    agent: dict,
    stance: str,
    prev_stance: str | None,
    rng: random.Random,
) -> str:
    demographics = agent.get("demographics") or {}
    values = {
        "occupation": demographics.get("occupation", "生活者"),
        "age": demographics.get("age", ""),
        "prev_stance": prev_stance,
    }
    style = agent.get("speech_style", "")
    changed = prev_stance is not None and prev_stance != stance
    if changed and rng.random() < 0.45:
        templates = CHANGE_TEMPLATES.get(style, {}).get(
            stance, FALLBACK_CHANGE_TEMPLATES[stance]
        )
    else:
        templates = BASE_TEMPLATES.get(style, {}).get(stance, FALLBACK_TEMPLATES[stance])
    result = rng.choice(templates).format(**values)

    life_event = str(agent.get("life_event") or "").strip()
    if life_event and rng.random() < 0.35:
        result = f"{result} {rng.choice(_LIFE_EVENT_ADDITIONS).format(life_event=life_event)}"
    return result


def generate_population_voices(
    changes: list[dict],
    agents_by_id: dict[str, dict],
    *,
    round_index: int,
    prev_stances: dict[str, str] | None = None,
    max_voices: int = 12,
    seed: int | None = None,
) -> list[dict]:
    """変化した非LLMエージェントを多様に抽出し、SSE用コメントを返す。"""
    if not changes or max_voices <= 0:
        return []

    rng = random.Random(_seed_value(seed, round_index))
    grouped: dict[str, list[dict]] = {stance: [] for stance in STANCE_ORDER}
    for change in changes:
        stance = change.get("stance")
        if stance in grouped and change.get("agent_id") in agents_by_id:
            grouped[stance].append(change)
    for group in grouped.values():
        rng.shuffle(group)

    selected: list[dict] = []
    while len(selected) < max_voices:
        added = False
        for stance in STANCE_ORDER:
            if grouped[stance] and len(selected) < max_voices:
                selected.append(grouped[stance].pop())
                added = True
        if not added:
            break

    previous = prev_stances or {}
    voices = []
    for change in selected:
        agent_id = change["agent_id"]
        agent = agents_by_id[agent_id]
        demographics = agent.get("demographics") or {}
        age = demographics.get("age", 0)
        prev_stance = previous.get(agent_id)
        voices.append({
            "agent_id": agent_id,
            "agent_index": change["agent_index"],
            "comment": _comment(agent, change["stance"], prev_stance, rng),
            "stance": change["stance"],
            "prev_stance": prev_stance,
            "occupation": demographics.get("occupation", ""),
            "age_bracket": age_bracket_5(age),
        })
    return voices
