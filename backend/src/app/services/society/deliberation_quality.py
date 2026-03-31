"""熟議品質評価モジュール

Discourse Quality Index (DQI) に基づく熟議プロセスの学術的評価。
参照: Steenbergen et al. (2003) "Measuring Political Deliberation:
A Discourse Quality Index", Comparative European Politics, 1(1), 21-48.

このモジュールは LLM 非依存のヒューリスティック版を提供する。
将来、compute_dqi を LLM 版に差し替えられるよう関数シグネチャを固定している。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Fishkin (1991, 2009) の Deliberative Poll における典型的な意見変化率
# 典型的な DP では参加者の 30–40% が意見を変える
_FISHKIN_TYPICAL_CHANGE_RATE_LOW = 0.30
_FISHKIN_TYPICAL_CHANGE_RATE_HIGH = 0.40

# DQI のヒューリスティック判定に使う表現リスト
_EMPATHY_EXPRESSIONS = ["わかる", "一理ある", "理解", "おっしゃる通り", "ご指摘の通り"]
_COMMON_GOOD_KEYWORDS = ["全体", "社会", "公共", "みんな", "国民", "市民", "共通"]
_CONDITIONAL_MARKERS = ["もし", "なら", "ならば", "であれば", "場合は", "条件"]
_PERSONAL_EXPERIENCE_MARKERS = ["うちの", "私の", "自分の", "我々の", "私たちの"]


# ---------------------------------------------------------------------------
# measure_opinion_change
# ---------------------------------------------------------------------------


def measure_opinion_change(meeting_rounds: list[list[dict]]) -> dict:
    """参加者の意見変化率を算出し、Fishkin の典型値と比較する。

    Args:
        meeting_rounds: ラウンドごとの発言リスト。各発言は ``participant`` と
            ``position`` キーを持つ辞書。

    Returns:
        {
            "change_rate": float,          # 変化した参加者の割合 (0–1)
            "changes": [                   # 変化した参加者のリスト
                {"participant": str, "from": str, "to": str}, ...
            ],
            "fishkin_comparison": str,     # Fishkin の典型値との比較コメント
        }
    """
    if len(meeting_rounds) < 2:
        return {
            "change_rate": 0.0,
            "changes": [],
            "fishkin_comparison": _build_fishkin_comparison(0.0),
        }

    first_round = meeting_rounds[0]
    last_round = meeting_rounds[-1]

    # participant → position の辞書を作る
    first_positions: dict[str, str] = {
        stmt["participant"]: stmt.get("position", "")
        for stmt in first_round
    }
    last_positions: dict[str, str] = {
        stmt["participant"]: stmt.get("position", "")
        for stmt in last_round
    }

    changes: list[dict[str, str]] = []
    all_participants = set(first_positions.keys()) & set(last_positions.keys())

    for participant in all_participants:
        pos_first = first_positions[participant]
        pos_last = last_positions[participant]
        if pos_first != pos_last:
            changes.append(
                {
                    "participant": participant,
                    "from": pos_first,
                    "to": pos_last,
                }
            )

    n_participants = len(all_participants)
    change_rate = len(changes) / n_participants if n_participants > 0 else 0.0

    return {
        "change_rate": round(change_rate, 4),
        "changes": changes,
        "fishkin_comparison": _build_fishkin_comparison(change_rate),
    }


def _build_fishkin_comparison(change_rate: float) -> str:
    """change_rate と Fishkin の典型値を比較したコメント文字列を返す。"""
    fishkin_range = (
        f"{int(_FISHKIN_TYPICAL_CHANGE_RATE_LOW * 100)}–"
        f"{int(_FISHKIN_TYPICAL_CHANGE_RATE_HIGH * 100)}%"
    )
    rate_pct = f"{change_rate * 100:.1f}%"

    if change_rate < _FISHKIN_TYPICAL_CHANGE_RATE_LOW:
        comparison = "下回る"
    elif change_rate <= _FISHKIN_TYPICAL_CHANGE_RATE_HIGH:
        comparison = "同等"
    else:
        comparison = "上回る"

    return (
        f"意見変化率 {rate_pct} は、Fishkin の熟議型世論調査における"
        f"典型的な変化率（{fishkin_range}）を{comparison}。"
    )


# ---------------------------------------------------------------------------
# compute_argument_quality
# ---------------------------------------------------------------------------


def compute_argument_quality(argument: str, evidence: str = "") -> dict:
    """単一発言の議論品質をヒューリスティックにスコアリングする。

    Args:
        argument: 発言テキスト。
        evidence: 根拠・データ文字列（空文字列の場合はなし）。

    Returns:
        {
            "evidence_score": float,               # 根拠の存在 (0 or 1)
            "counterargument_score": float,        # 反論への応答 (0 or 1)
            "conditional_reasoning_score": float,  # 条件付き推論 (0 or 1)
            "personal_experience_score": float,    # 個人体験の共有 (0 or 1)
            "overall": float,                      # 4 スコアの平均
        }
    """
    if not argument and not evidence:
        return {
            "evidence_score": 0.0,
            "counterargument_score": 0.0,
            "conditional_reasoning_score": 0.0,
            "personal_experience_score": 0.0,
            "overall": 0.0,
        }

    # evidence_score: evidence フィールドが非空 OR argument 中に数値・% などが含まれる
    evidence_score = 1.0 if evidence.strip() else 0.0

    # counterargument_score: 共感・応答表現を含む
    counterargument_score = (
        1.0
        if any(expr in argument for expr in _EMPATHY_EXPRESSIONS)
        else 0.0
    )

    # conditional_reasoning_score: 条件マーカーを含む
    conditional_reasoning_score = (
        1.0
        if any(marker in argument for marker in _CONDITIONAL_MARKERS)
        else 0.0
    )

    # personal_experience_score: 個人体験マーカーを含む
    personal_experience_score = (
        1.0
        if any(marker in argument for marker in _PERSONAL_EXPERIENCE_MARKERS)
        else 0.0
    )

    components = [
        evidence_score,
        counterargument_score,
        conditional_reasoning_score,
        personal_experience_score,
    ]
    overall = sum(components) / len(components)

    return {
        "evidence_score": evidence_score,
        "counterargument_score": counterargument_score,
        "conditional_reasoning_score": conditional_reasoning_score,
        "personal_experience_score": personal_experience_score,
        "overall": overall,
    }


# ---------------------------------------------------------------------------
# compute_dqi (ヒューリスティック版)
# ---------------------------------------------------------------------------


def compute_dqi(meeting_rounds: list[list[dict]]) -> dict:
    """Discourse Quality Index の 5 次元をヒューリスティックに算出する。

    DQI の 5 次元 (Steenbergen et al. 2003):
        1. justification_level       — 根拠付きの発言割合
        2. justification_content     — 共通利益への言及割合
        3. respect_groups            — 他者への敬意表現割合
        4. respect_counterarguments  — 反論への直接応答割合
        5. constructive_politics     — 建設的提案（質問や代替案）割合

    Args:
        meeting_rounds: ラウンドごとの発言リスト。

    Returns:
        {
            "dimensions": {
                "justification_level": float,
                "justification_content": float,
                "respect_groups": float,
                "respect_counterarguments": float,
                "constructive_politics": float,
            },
            "overall_dqi": float,   # 5 次元の平均
        }
    """
    # 全ラウンドを平坦化
    all_statements: list[dict[str, Any]] = [
        stmt for rnd in meeting_rounds for stmt in rnd
    ]

    n = len(all_statements)

    if n == 0:
        dimensions = {
            "justification_level": 0.0,
            "justification_content": 0.0,
            "respect_groups": 0.0,
            "respect_counterarguments": 0.0,
            "constructive_politics": 0.0,
        }
        return {"dimensions": dimensions, "overall_dqi": 0.0}

    # 1. justification_level: evidence が非空の発言の割合
    justification_level = sum(
        1 for s in all_statements if s.get("evidence", "").strip()
    ) / n

    # 2. justification_content: concerns に共通利益ワードを含む発言の割合
    def _has_common_good(stmt: dict) -> bool:
        concerns = stmt.get("concerns", [])
        argument = stmt.get("argument", "")
        text = argument + " ".join(concerns)
        return any(kw in text for kw in _COMMON_GOOD_KEYWORDS)

    justification_content = sum(
        1 for s in all_statements if _has_common_good(s)
    ) / n

    # 3. respect_groups: argument に共感・敬意表現を含む発言の割合
    respect_groups = sum(
        1
        for s in all_statements
        if any(expr in s.get("argument", "") for expr in _EMPATHY_EXPRESSIONS)
    ) / n

    # 4. respect_counterarguments: addressed_to が非空（反論に直接応答）の割合
    respect_counterarguments = sum(
        1 for s in all_statements if s.get("addressed_to", "").strip()
    ) / n

    # 5. constructive_politics: questions_to_others が非空 OR 条件マーカーを含む割合
    def _is_constructive(stmt: dict) -> bool:
        has_questions = bool(stmt.get("questions_to_others", []))
        has_alternative = any(
            marker in stmt.get("argument", "") for marker in _CONDITIONAL_MARKERS
        )
        return has_questions or has_alternative

    constructive_politics = sum(
        1 for s in all_statements if _is_constructive(s)
    ) / n

    raw_dimensions = {
        "justification_level": justification_level,
        "justification_content": justification_content,
        "respect_groups": respect_groups,
        "respect_counterarguments": respect_counterarguments,
        "constructive_politics": constructive_politics,
    }
    overall_dqi = sum(raw_dimensions.values()) / len(raw_dimensions)
    dimensions = {k: round(v, 4) for k, v in raw_dimensions.items()}

    return {"dimensions": dimensions, "overall_dqi": round(overall_dqi, 4)}
