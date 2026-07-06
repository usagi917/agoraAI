"""Decision Brief のスキーマ正規化。

LLM が返す brief dict はフィールド欠損・型不一致が起こりうるため、
レンダリング（frontend / decision_briefing.py / synthesis の narrative）前に
必須フィールドをデフォルト充填し、型を強制する。修復した内容は
schema_repair_warnings に記録し、品質問題を追跡可能にする。

このモジュールは *スキーマ*（型・必須フィールド・要素構造）の正規化のみを行い、
HTML / Markdown のサニタイズは行わない。文字列値のエスケープ・サニタイズは
描画シンク（現状は frontend の DOMPurify）の責務であり、ここでは扱わない。
"""

import math
from typing import Any

from src.app.services.decision_briefing import RECOMMENDATION_CONDITIONAL_GO

# field -> default
_STR_FIELDS: dict[str, str] = {
    "recommendation": RECOMMENDATION_CONDITIONAL_GO,
    "decision_summary": "",
    "why_now": "",
    "confidence_explainer": "",
    "strongest_counterargument": "",
}

# list フィールドのうち、要素が dict 前提のもの。値は各要素の「主要テキストフィールド」で、
# 非 dict 要素はこのキーに包んで情報を保持する（dict 前提の消費側での欠落/クラッシュを防ぐ）。
#
# 消費側の内訳:
#   - key_reasons / guardrails / deal_breakers / critical_unknowns / next_decisions /
#     recommended_actions / decision_scorecard / risk_factors:
#       Python レンダラー（decision_briefing.render_decision_brief_markdown /
#       synthesis の narrative renderer）が item.get(...) で消費するため、
#       非 dict 要素は AttributeError の直接原因になる。
#   - option_comparison / stakeholder_reactions:
#       Python レンダラーは読まず frontend（DecisionBrief.vue）のみが消費する。
#       クラッシュ安全性ではなく表示品質のために正規化対象へ残す（マップから外さない）。
_DICT_ITEM_FIELDS: dict[str, str] = {
    "key_reasons": "reason",
    "guardrails": "condition",
    "deal_breakers": "trigger",
    "critical_unknowns": "question",
    "next_decisions": "decision",
    "recommended_actions": "action",
    "option_comparison": "label",
    "risk_factors": "condition",
    "stakeholder_reactions": "reaction",
    "decision_scorecard": "label",
}

# list フィールドのうち、要素が str 前提のもの（レンダラーが _clean_text / f-string で消費）。
_STR_ITEM_FIELDS = (
    "evidence_gaps",
    "next_steps",
)

_DICT_FIELDS = (
    "agreement_breakdown",
    "time_horizon",
)

# time_horizon の既知サブキー。値は dict 前提（narrative renderer が period.get(...) で消費）。
_TIME_HORIZON_KEYS = (
    "short_term",
    "mid_term",
    "long_term",
)

# conversation_highlights（dict）内のネスト list。各要素は dict 前提
# （render_decision_brief_markdown が item.get(...) で消費）。
_HIGHLIGHT_ITEM_FIELDS: dict[str, str] = {
    "consensus": "point",
    "conflicts": "point",
    "turning_points": "moment",
    "key_quotes": "quote",
}


def normalize_decision_brief(brief: dict | None) -> dict:
    """brief を正規化した *浅いコピー* を返す。

    トップレベルのキーは新しい dict / list に載せ替えるため、入力の
    トップレベル dict は変更しない。ただし変更不要でそのまま通過する
    ネストした dict / list 要素は入力と参照を共有する（deep copy はしない）。

    - 欠損 / None フィールドはデフォルト値で充填
    - str 期待フィールドに非 str → str() 変換
    - list 期待フィールドに単一値 → [value] にラップ
    - dict 要素前提の list は非 dict 要素を {主キー: value} に包む（情報保持）
    - str 要素前提の list は非 str 要素を str() 変換（None → ""）
    - dict 期待フィールドに非 dict → デフォルトに置換
    - time_horizon / conversation_highlights のネスト構造も要素単位で正規化
    - agreement_score は float に強制し 0-1 に clamp（NaN/inf は 0.5）
    - 修復が発生した場合のみ schema_repair_warnings を付与
    """
    out: dict[str, Any] = dict(brief or {})
    warnings: list[str] = []

    for field, default in _STR_FIELDS.items():
        value = out.get(field)
        if value is None:
            out[field] = default
        elif not isinstance(value, str):
            out[field] = str(value)
            warnings.append(f"{field}: coerced {type(value).__name__} to str")

    for field, item_key in _DICT_ITEM_FIELDS.items():
        items = _as_list_field(out, field, warnings)
        out[field] = _normalize_dict_items(field, items, item_key, warnings)

    for field in _STR_ITEM_FIELDS:
        items = _as_list_field(out, field, warnings)
        normalized_str: list[Any] = []
        for item in items:
            if isinstance(item, str):
                normalized_str.append(item)
            elif item is None:
                normalized_str.append("")
            else:
                normalized_str.append(str(item))
                warnings.append(f"{field}: coerced {type(item).__name__} item to str")
        out[field] = normalized_str

    for field in _DICT_FIELDS:
        value = out.get(field)
        if value is None:
            out[field] = {}
        elif not isinstance(value, dict):
            out[field] = {}
            warnings.append(f"{field}: replaced invalid {type(value).__name__} with empty dict")

    _normalize_time_horizon(out, warnings)
    _normalize_conversation_highlights(out, warnings)

    score = out.get("agreement_score")
    if score is None:
        out["agreement_score"] = 0.5
    elif isinstance(score, (int, float)) and not isinstance(score, bool):
        numeric = float(score)
        if math.isfinite(numeric):
            out["agreement_score"] = min(1.0, max(0.0, numeric))
        else:
            out["agreement_score"] = 0.5
            warnings.append(f"agreement_score: replaced non-finite {numeric} with 0.5")
    else:
        out["agreement_score"] = 0.5
        warnings.append(f"agreement_score: replaced invalid {type(score).__name__} with 0.5")

    if warnings:
        existing = out.get("schema_repair_warnings")
        out["schema_repair_warnings"] = (existing if isinstance(existing, list) else []) + warnings

    return out


def _as_list_field(out: dict[str, Any], field: str, warnings: list[str]) -> list[Any]:
    """out[field] を list として取り出す。None は []、非 list は [value] にラップ。

    ラップした場合は warnings に記録する（要素の正規化は呼び出し側が行う）。
    """
    value = out.get(field)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    warnings.append(f"{field}: wrapped {type(value).__name__} into list")
    return [value]


def _normalize_dict_items(
    field: str, items: list[Any], item_key: str, warnings: list[str]
) -> list[Any]:
    """dict 要素前提の list を正規化する。非 dict 要素を {item_key: value} に包む。"""
    normalized: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({item_key: item})
            warnings.append(
                f"{field}: wrapped {type(item).__name__} item into {{'{item_key}': ...}}"
            )
    return normalized


def _normalize_time_horizon(out: dict[str, Any], warnings: list[str]) -> None:
    """time_horizon の既知サブキー値が非 dict なら {'prediction': str(値)} に包む。

    narrative renderer は period.get('period') / period.get('prediction') と
    dict 前提で消費するため、非 dict サブ値は AttributeError の原因になる。
    """
    time_horizon = out.get("time_horizon")
    if not isinstance(time_horizon, dict):
        return
    normalized = dict(time_horizon)
    for period_key in _TIME_HORIZON_KEYS:
        sub = normalized.get(period_key)
        if sub is not None and not isinstance(sub, dict):
            normalized[period_key] = {"prediction": str(sub)}
            warnings.append(
                f"time_horizon.{period_key}: wrapped {type(sub).__name__} into {{'prediction': ...}}"
            )
    out["time_horizon"] = normalized


def _normalize_conversation_highlights(out: dict[str, Any], warnings: list[str]) -> None:
    """conversation_highlights が dict の場合、ネスト list を要素単位で正規化する。

    非 dict の conversation_highlights はレンダラーが isinstance(dict) で弾くため
    そのまま通す。存在するネスト list のみ正規化し、欠損キーは補充しない。
    """
    highlights = out.get("conversation_highlights")
    if not isinstance(highlights, dict):
        return
    normalized = dict(highlights)
    for key, item_key in _HIGHLIGHT_ITEM_FIELDS.items():
        raw = normalized.get(key)
        if raw is None:
            continue
        field = f"conversation_highlights.{key}"
        if isinstance(raw, list):
            items = raw
        else:
            items = [raw]
            warnings.append(f"{field}: wrapped {type(raw).__name__} into list")
        normalized[key] = _normalize_dict_items(field, items, item_key, warnings)
    out["conversation_highlights"] = normalized
