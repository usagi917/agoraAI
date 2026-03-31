"""デモグラフィック・クロス分析: Activation回答をデモグラフィック属性ごとに集計する"""

from collections import Counter

from src.app.services.society.age_utils import age_bracket_5 as _age_bracket


def _compute_stance_by_group(
    agents: list[dict],
    responses: list[dict],
    group_fn,
) -> dict:
    """グループ関数でエージェントを分け、各グループ内のスタンス分布を集計する。"""
    groups: dict[str, list[str]] = {}

    for agent, resp in zip(agents, responses):
        group = group_fn(agent)
        stance = resp.get("stance", "不明")
        if group not in groups:
            groups[group] = []
        groups[group].append(stance)

    result = {}
    for group, stances in sorted(groups.items()):
        total = len(stances)
        counter = Counter(stances)
        result[group] = {
            "total": total,
            "distribution": {
                s: round(c / total, 4) for s, c in counter.most_common()
            },
        }
    return result


def analyze_demographics(
    agents: list[dict],
    responses: list[dict],
) -> dict:
    """デモグラフィック×スタンスのクロス分析を実行する。

    Returns:
        {
            "by_age": { "18-29": { "total": 10, "distribution": { "賛成": 0.3, ... } }, ... },
            "by_region": { ... },
            "by_occupation": { ... },
            "by_income": { ... },
            "by_education": { ... },
        }
    """
    if not agents or not responses:
        return {}

    return {
        "by_age": _compute_stance_by_group(
            agents, responses,
            lambda a: _age_bracket(a.get("demographics", {}).get("age", 0)),
        ),
        "by_region": _compute_stance_by_group(
            agents, responses,
            lambda a: a.get("demographics", {}).get("region", "不明"),
        ),
        "by_occupation": _compute_stance_by_group(
            agents, responses,
            lambda a: a.get("demographics", {}).get("occupation", "不明"),
        ),
        "by_income": _compute_stance_by_group(
            agents, responses,
            lambda a: a.get("demographics", {}).get("income_bracket", "不明"),
        ),
        "by_education": _compute_stance_by_group(
            agents, responses,
            lambda a: a.get("demographics", {}).get("education", "不明"),
        ),
    }
