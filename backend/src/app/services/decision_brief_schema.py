"""Decision Brief のスキーマ正規化。

LLM が返す brief dict はフィールド欠損・型不一致が起こりうるため、
レンダリング（frontend / decision_briefing.py）前に必須フィールドを
デフォルト充填し、型を強制する。修復した内容は schema_repair_warnings
に記録し、品質問題を追跡可能にする。
"""

from typing import Any

# field -> (expected_type, default)
_STR_FIELDS: dict[str, str] = {
    "recommendation": "条件付きGo",
    "decision_summary": "",
    "why_now": "",
    "confidence_explainer": "",
    "strongest_counterargument": "",
}

_LIST_FIELDS = (
    "key_reasons",
    "guardrails",
    "deal_breakers",
    "critical_unknowns",
    "next_decisions",
    "recommended_actions",
    "option_comparison",
    "evidence_gaps",
    "risk_factors",
    "next_steps",
    "stakeholder_reactions",
)

_DICT_FIELDS = (
    "agreement_breakdown",
    "time_horizon",
)


def normalize_decision_brief(brief: dict | None) -> dict:
    """brief を正規化したコピーを返す（入力は変更しない）。

    - 欠損 / None フィールドはデフォルト値で充填
    - str 期待フィールドに非 str → str() 変換
    - list 期待フィールドに単一値 → [value] にラップ
    - dict 期待フィールドに非 dict → デフォルトに置換
    - agreement_score は float に強制し 0-1 に clamp
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

    for field in _LIST_FIELDS:
        value = out.get(field)
        if value is None:
            out[field] = []
        elif not isinstance(value, list):
            out[field] = [value]
            warnings.append(f"{field}: wrapped {type(value).__name__} into list")

    for field in _DICT_FIELDS:
        value = out.get(field)
        if value is None:
            out[field] = {}
        elif not isinstance(value, dict):
            out[field] = {}
            warnings.append(f"{field}: replaced invalid {type(value).__name__} with empty dict")

    score = out.get("agreement_score")
    if score is None:
        out["agreement_score"] = 0.5
    elif isinstance(score, (int, float)) and not isinstance(score, bool):
        out["agreement_score"] = min(1.0, max(0.0, float(score)))
    else:
        out["agreement_score"] = 0.5
        warnings.append(f"agreement_score: replaced invalid {type(score).__name__} with 0.5")

    if warnings:
        existing = out.get("schema_repair_warnings")
        out["schema_repair_warnings"] = (existing if isinstance(existing, list) else []) + warnings

    return out
