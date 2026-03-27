"""人口生成サービス: 統計的サンプリングで住民プロフィールを生成（LLM不要）"""

import logging
import random
import uuid
from typing import Any

from src.app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_POPULATION_SIZE = 1000
DEFAULT_MIN_POPULATION_SIZE = 100
DEFAULT_MAX_POPULATION_SIZE = 10000

# 職業リスト（地域・教育レベル別に重み付け）
OCCUPATIONS = [
    "会社員", "公務員", "教師", "医師", "看護師", "エンジニア", "研究者",
    "営業職", "事務職", "自営業", "農業", "漁業", "建設作業員", "運転手",
    "販売員", "飲食店員", "介護士", "弁護士", "会計士", "デザイナー",
    "フリーランス", "学生", "主婦/主夫", "退職者", "パート/アルバイト",
    "経営者", "コンサルタント", "記者", "芸術家", "薬剤師",
]

REGIONS = [
    "北海道", "東北", "関東（都市部）", "関東（郊外）", "中部",
    "関西（都市部）", "関西（郊外）", "中国", "四国", "九州", "沖縄",
]

# 2020年国勢調査（令和2年）都道府県別人口比
REGION_WEIGHTS = [0.041, 0.070, 0.292, 0.053, 0.168, 0.134, 0.043, 0.057, 0.029, 0.101, 0.012]

# 2020年国勢調査 18歳以上の年齢分布（min, max, weight）
AGE_BRACKETS: list[tuple[int, int, float]] = [
    (18, 24, 0.079),
    (25, 29, 0.058),
    (30, 34, 0.059),
    (35, 39, 0.068),
    (40, 44, 0.083),
    (45, 49, 0.090),
    (50, 54, 0.085),
    (55, 59, 0.076),
    (60, 64, 0.072),
    (65, 69, 0.082),
    (70, 74, 0.088),
    (75, 79, 0.059),
    (80, 84, 0.038),
    (85, 90, 0.063),
]

# 総務省労働力調査・国税庁データに基づく職業別就業人口ウェイト（OCCUPATIONS と同順）
OCCUPATION_WEIGHTS = [
    0.210, 0.035, 0.012, 0.003, 0.012, 0.023, 0.006,
    0.041, 0.052, 0.041, 0.023, 0.002, 0.035, 0.023,
    0.041, 0.035, 0.023, 0.001, 0.005, 0.008,
    0.029, 0.035, 0.082, 0.105, 0.082,
    0.023, 0.006, 0.001, 0.003, 0.003,
]

INFORMATION_SOURCES = [
    "テレビニュース", "新聞", "SNS(Twitter/X)", "SNS(Instagram)", "YouTube",
    "LINE NEWS", "Yahoo!ニュース", "NHK", "専門誌", "口コミ・友人",
    "ポッドキャスト", "地域コミュニティ", "職場の同僚", "家族",
]

LIFE_EVENTS = [
    "最近転職した", "子供が生まれた", "親の介護をしている", "住宅ローンを組んだ",
    "病気を経験した", "昇進した", "失業した", "留学から帰国した",
    "結婚した", "離婚した", "退職した", "引っ越した",
    "起業した", "資格を取得した", "投資で損をした",
    "", "", "", "",  # 特になし（確率を上げる）
]

VALUE_DIMENSIONS = [
    ("安全・安定", "security"), ("自由・自律", "freedom"),
    ("伝統・保守", "tradition"), ("革新・変化", "innovation"),
    ("公平・平等", "fairness"), ("効率・成果", "efficiency"),
    ("環境・持続可能性", "environment"), ("経済成長", "growth"),
    ("個人の権利", "individual_rights"), ("共同体・連帯", "community"),
]

SPEECH_STYLES = [
    "丁寧で慎重", "率直で簡潔", "感情的で熱心", "分析的で論理的",
    "ユーモアを交える", "控えめで消極的", "攻撃的で主張が強い",
    "共感的で聞き上手", "皮肉っぽい", "楽観的",
]


def _sample_categorical(categories: list[str], weights: list[float]) -> str:
    return random.choices(categories, weights=weights, k=1)[0]


def _sample_age_from_census(min_age: int = 18, max_age: int = 85) -> int:
    """2020年国勢調査の年齢分布に基づいて年齢をサンプリングする。"""
    eligible_brackets = []
    eligible_weights = []
    for start, end, weight in AGE_BRACKETS:
        clipped_start = max(start, min_age)
        clipped_end = min(end, max_age)
        if clipped_start <= clipped_end:
            eligible_brackets.append((clipped_start, clipped_end))
            eligible_weights.append(weight)

    if not eligible_brackets:
        return min_age

    bracket = random.choices(eligible_brackets, weights=eligible_weights, k=1)[0]
    return random.randint(bracket[0], bracket[1])


def _sample_age(age_cfg: dict) -> int:
    """設定に応じて年齢をサンプリングする。"""
    distribution = age_cfg.get("distribution", "normal")
    min_age = age_cfg.get("min", 18)
    max_age = age_cfg.get("max", 85)

    if distribution == "census":
        return _sample_age_from_census(min_age=min_age, max_age=max_age)

    mean = age_cfg.get("mean", 42)
    std = age_cfg.get("std", 15)
    return int(_sample_normal_clamped(mean, std, min_age, max_age))


def _sample_normal_clamped(mean: float, std: float, low: float = 0.0, high: float = 1.0) -> float:
    value = random.gauss(mean, std)
    return max(low, min(high, value))


def get_population_size_bounds() -> tuple[int, int, int]:
    """人口サイズのデフォルト値と許容範囲を設定から解決する。"""
    mix_config = settings.load_population_mix_config()
    pop_config = mix_config.get("population", {})

    default_size = int(pop_config.get("default_size", DEFAULT_POPULATION_SIZE))
    min_size = int(pop_config.get("min_size", DEFAULT_MIN_POPULATION_SIZE))
    max_size = int(pop_config.get("max_size", DEFAULT_MAX_POPULATION_SIZE))

    min_size, max_size = sorted((min_size, max_size))
    default_size = max(min_size, min(max_size, default_size))
    return default_size, min_size, max_size


def get_default_population_size() -> int:
    return get_population_size_bounds()[0]


def validate_population_size(count: int) -> int:
    """人口サイズが設定された範囲内かを検証する。"""
    _, min_size, max_size = get_population_size_bounds()
    if count < min_size or count > max_size:
        raise ValueError(f"count は {min_size}〜{max_size} の範囲で指定してください")
    return count


def _generate_demographics(pop_config: dict) -> dict:
    """人口統計情報を生成する。"""
    demo_cfg = pop_config.get("demographics", {})

    age = _sample_age(demo_cfg.get("age", {}))

    gender_cfg = demo_cfg.get("gender", {}).get("weights", {"male": 0.49, "female": 0.49, "other": 0.02})
    gender = _sample_categorical(list(gender_cfg.keys()), list(gender_cfg.values()))

    edu_cfg = demo_cfg.get("education", {}).get("weights", {
        "high_school": 0.30, "bachelor": 0.35, "master": 0.20,
        "doctorate": 0.05, "vocational": 0.10,
    })
    education = _sample_categorical(list(edu_cfg.keys()), list(edu_cfg.values()))

    income_cfg = demo_cfg.get("income_bracket", {}).get("weights", {
        "low": 0.25, "lower_middle": 0.25, "upper_middle": 0.30,
        "high": 0.15, "very_high": 0.05,
    })
    income_bracket = _sample_categorical(list(income_cfg.keys()), list(income_cfg.values()))

    region = _sample_categorical(REGIONS, REGION_WEIGHTS)
    occupation = _sample_categorical(OCCUPATIONS, OCCUPATION_WEIGHTS)

    return {
        "age": age,
        "gender": gender,
        "occupation": occupation,
        "region": region,
        "income_bracket": income_bracket,
        "education": education,
    }


def _generate_big_five(pop_config: dict) -> dict:
    """Big Five パーソナリティ特性を生成する。"""
    bf_cfg = pop_config.get("big_five", {})
    mean = bf_cfg.get("mean", 0.5)
    std = bf_cfg.get("std", 0.2)

    return {
        "O": round(_sample_normal_clamped(mean, std), 3),  # Openness
        "C": round(_sample_normal_clamped(mean, std), 3),  # Conscientiousness
        "E": round(_sample_normal_clamped(mean, std), 3),  # Extraversion
        "A": round(_sample_normal_clamped(mean, std), 3),  # Agreeableness
        "N": round(_sample_normal_clamped(mean, std), 3),  # Neuroticism
    }


def _generate_values() -> dict:
    """価値観リスト + 重みを生成する。"""
    # 3-5個の価値観を選択し、重みを割り当てる
    count = random.randint(3, 5)
    selected = random.sample(VALUE_DIMENSIONS, count)
    weights = [random.uniform(0.3, 1.0) for _ in selected]
    total = sum(weights)
    return {key: round(w / total, 3) for (_, key), w in zip(selected, weights)}


def _generate_shock_sensitivity() -> dict:
    """トピック別ショック感応度を生成する。"""
    topics = [
        "economy", "technology", "environment", "health", "education",
        "security", "immigration", "taxation", "welfare", "energy",
    ]
    # 各住民は2-5トピックに高い感応度を持つ
    high_count = random.randint(2, 5)
    high_topics = random.sample(topics, high_count)
    result = {}
    for t in topics:
        if t in high_topics:
            result[t] = round(random.uniform(0.6, 1.0), 3)
        else:
            result[t] = round(random.uniform(0.0, 0.4), 3)
    return result


def _assign_llm_backend(index: int, total: int, mix_config: dict) -> str:
    """人口ミックス設定に基づいてLLMバックエンドを割り当てる。"""
    activation_cfg = mix_config.get("activation_layer", {})
    weights = activation_cfg.get("weights", {"openai": 0.5, "gemini": 0.3, "anthropic": 0.2})

    providers = list(weights.keys())
    probs = list(weights.values())
    return _sample_categorical(providers, probs)


def _generate_contradiction(big_five: dict, values: dict) -> str:
    """Big Five traits と values の矛盾から内面的葛藤を生成する（ルールベース）。"""
    contradictions = []

    o = big_five.get("O", 0.5)
    a = big_five.get("A", 0.5)
    e = big_five.get("E", 0.5)
    n = big_five.get("N", 0.5)
    c = big_five.get("C", 0.5)

    value_keys = set(values.keys())

    # 開放性が高いが伝統を重視
    if o > 0.65 and "tradition" in value_keys:
        contradictions.append("新しいものに惹かれるが、伝統も捨てきれない")
    # 協調性が高いが個人の自由を重視
    if a > 0.65 and "freedom" in value_keys:
        contradictions.append("協調的だが個人の自由を強く求める矛盾を抱えている")
    # 神経症傾向が高いが成長志向
    if n > 0.65 and "growth" in value_keys:
        contradictions.append("不安を感じやすいが経済成長への期待も強い")
    # 外向性が低いがコミュニティ重視
    if e < 0.35 and "community" in value_keys:
        contradictions.append("内向的だがコミュニティの絆を重視している")
    # 誠実性が高いが革新志向
    if c > 0.65 and "innovation" in value_keys:
        contradictions.append("計画的で慎重だが変化を求める気持ちもある")
    # 安全志向と自由志向が共存
    if "security" in value_keys and "freedom" in value_keys:
        contradictions.append("安定を求めながらも自由に生きたい")

    if contradictions:
        return random.choice(contradictions)
    return ""


def _generate_hidden_motivation(
    demographics: dict, life_event: str, values: dict
) -> str:
    """life_event と income/occupation から隠された動機を生成する（ルールベース）。"""
    income = demographics.get("income_bracket", "")
    occupation = demographics.get("occupation", "")
    age = demographics.get("age", 40)

    motivations = []

    # 経済的状況に基づく動機
    if income in ("low", "lower_middle"):
        if life_event == "失業した":
            motivations.append("経済的不安から雇用安定を最優先する")
        elif life_event == "投資で損をした":
            motivations.append("損失の経験からリスク回避を強く求める")
        else:
            motivations.append("生活費の負担から経済的な支援策に敏感")
    elif income in ("high", "very_high"):
        if "growth" in values:
            motivations.append("さらなる資産形成と事業拡大の機会を狙っている")
        else:
            motivations.append("現在の生活水準を維持するための安定策を重視")

    # ライフイベントに基づく動機
    if life_event == "子供が生まれた":
        motivations.append("子供の将来のために社会の安全性を最優先している")
    elif life_event == "親の介護をしている":
        motivations.append("介護負担から福祉・医療制度の充実を切実に求めている")
    elif life_event == "起業した":
        motivations.append("事業の成功のためにビジネス環境の改善を望んでいる")
    elif life_event == "退職した":
        motivations.append("年金と医療の安定確保が最大の関心事")

    # 年齢に基づく動機
    if age < 30:
        motivations.append("将来への不確実性から長期的なキャリア展望を気にしている")
    elif age > 65:
        motivations.append("残りの人生の安心のために社会保障を重視")

    if motivations:
        return random.choice(motivations)
    return ""


def _generate_memory_summary(demographics: dict, life_event: str) -> str:
    """region + occupation + life_event から生活要約を生成する。"""
    region = demographics.get("region", "不明")
    occupation = demographics.get("occupation", "不明")
    age = demographics.get("age", "不明")

    summary = f"{region}で{occupation}として働く{age}歳"
    if life_event:
        summary += f"。{life_event}"
    return summary


def generate_agent_profile(
    index: int,
    population_id: str,
    pop_config: dict,
    mix_config: dict,
    total: int,
) -> dict[str, Any]:
    """1人分の住民プロフィールを生成する。"""
    demographics = _generate_demographics(pop_config)
    big_five = _generate_big_five(pop_config)
    values = _generate_values()
    life_event = random.choice(LIFE_EVENTS)

    return {
        "id": str(uuid.uuid4()),
        "population_id": population_id,
        "agent_index": index,
        "demographics": demographics,
        "big_five": big_five,
        "values": values,
        "life_event": life_event,
        "contradiction": _generate_contradiction(big_five, values),
        "information_source": random.choice(INFORMATION_SOURCES),
        "local_context": f"{demographics['region']}在住の{demographics['occupation']}",
        "hidden_motivation": _generate_hidden_motivation(demographics, life_event, values),
        "speech_style": random.choice(SPEECH_STYLES),
        "shock_sensitivity": _generate_shock_sensitivity(),
        "llm_backend": _assign_llm_backend(index, total, mix_config),
        "memory_summary": _generate_memory_summary(demographics, life_event),
    }


async def generate_population(
    population_id: str,
    count: int | None = None,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """指定人数の住民プロフィールを一括生成する。

    LLM は使用しない。統計的サンプリングのみ。
    """
    resolved_count = get_default_population_size() if count is None else int(count)
    if resolved_count <= 0:
        raise ValueError("count must be positive")

    if seed is not None:
        random.seed(seed)

    mix_config = settings.load_population_mix_config()
    pop_config = mix_config.get("population", {})

    agents = []
    for i in range(resolved_count):
        profile = generate_agent_profile(i, population_id, pop_config, mix_config, resolved_count)
        agents.append(profile)

    logger.info("Generated %d agent profiles for population %s", resolved_count, population_id)
    return agents
