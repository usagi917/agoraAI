"""Decision Brief の正規化（スキーマ検証・デフォルト充填）テスト"""

from src.app.services.decision_brief_schema import normalize_decision_brief
from src.app.services.decision_briefing import render_decision_brief_markdown


class TestNormalizeDecisionBrief:
    def test_fills_missing_fields_with_defaults(self):
        brief = normalize_decision_brief({})
        assert brief["recommendation"] == "条件付きGo"
        assert brief["decision_summary"] == ""
        assert brief["key_reasons"] == []
        assert brief["evidence_gaps"] == []
        assert brief["next_steps"] == []
        assert brief["time_horizon"] == {}
        assert brief["stakeholder_reactions"] == []
        assert 0.0 <= brief["agreement_score"] <= 1.0

    def test_preserves_valid_fields(self):
        src = {
            "recommendation": "Go",
            "decision_summary": "進めるべき",
            "key_reasons": [{"reason": "r", "evidence": "e", "confidence": 0.8}],
            "agreement_score": 0.7,
        }
        brief = normalize_decision_brief(src)
        assert brief["recommendation"] == "Go"
        assert brief["decision_summary"] == "進めるべき"
        assert brief["key_reasons"] == src["key_reasons"]
        assert brief["agreement_score"] == 0.7
        # 正常な入力では修復警告なし
        assert "schema_repair_warnings" not in brief

    def test_coerces_str_to_list(self):
        brief = normalize_decision_brief({"next_steps": "追加調査"})
        assert brief["next_steps"] == ["追加調査"]
        assert any("next_steps" in w for w in brief["schema_repair_warnings"])

    def test_replaces_invalid_dict_with_default(self):
        brief = normalize_decision_brief({"time_horizon": "3ヶ月後"})
        assert brief["time_horizon"] == {}
        assert any("time_horizon" in w for w in brief["schema_repair_warnings"])

    def test_clamps_agreement_score(self):
        assert normalize_decision_brief({"agreement_score": 1.8})["agreement_score"] == 1.0
        assert normalize_decision_brief({"agreement_score": -0.2})["agreement_score"] == 0.0

    def test_invalid_agreement_score_defaults(self):
        brief = normalize_decision_brief({"agreement_score": "high"})
        assert brief["agreement_score"] == 0.5
        assert any("agreement_score" in w for w in brief["schema_repair_warnings"])

    def test_none_values_treated_as_missing(self):
        brief = normalize_decision_brief({"key_reasons": None, "decision_summary": None})
        assert brief["key_reasons"] == []
        assert brief["decision_summary"] == ""

    def test_keeps_unknown_extra_fields(self):
        brief = normalize_decision_brief({"conversation_highlights": [{"quote": "x"}]})
        assert brief["conversation_highlights"] == [{"quote": "x"}]

    def test_does_not_mutate_input(self):
        src = {"next_steps": "str-value"}
        normalize_decision_brief(src)
        assert src == {"next_steps": "str-value"}


class TestNormalizeListElements:
    """dict 要素前提 / str 要素前提の list について、要素単位の型正規化を検証する。"""

    def test_wraps_str_element_into_dict_for_dict_field(self):
        # key_reasons は要素が dict 前提（レンダラーが item.get("reason")）
        brief = normalize_decision_brief({"key_reasons": ["ただのテキスト"]})
        assert brief["key_reasons"] == [{"reason": "ただのテキスト"}]
        assert any("key_reasons" in w for w in brief["schema_repair_warnings"])

    def test_wraps_numeric_element_into_dict(self):
        brief = normalize_decision_brief({"risk_factors": [42]})
        assert brief["risk_factors"] == [{"condition": 42}]
        assert any("risk_factors" in w for w in brief["schema_repair_warnings"])

    def test_guardrails_mixed_str_and_dict_elements(self):
        brief = normalize_decision_brief({"guardrails": ["前提A", {"condition": "前提B"}]})
        assert brief["guardrails"] == [{"condition": "前提A"}, {"condition": "前提B"}]

    def test_recommended_actions_str_and_numeric_elements(self):
        brief = normalize_decision_brief({"recommended_actions": ["すぐ実行", 7]})
        assert brief["recommended_actions"] == [{"action": "すぐ実行"}, {"action": 7}]

    def test_scalar_field_wrapped_then_element_wrapped(self):
        # 単一スカラ → list 化 → 要素も dict 化される
        brief = normalize_decision_brief({"key_reasons": "単一根拠"})
        assert brief["key_reasons"] == [{"reason": "単一根拠"}]

    def test_preserves_valid_dict_elements_without_warning(self):
        src = {"key_reasons": [{"reason": "r", "evidence": "e"}]}
        brief = normalize_decision_brief(src)
        assert brief["key_reasons"] == [{"reason": "r", "evidence": "e"}]
        assert "schema_repair_warnings" not in brief

    def test_str_item_field_coerces_non_str_element(self):
        brief = normalize_decision_brief({"next_steps": [123, "調査"]})
        assert brief["next_steps"] == ["123", "調査"]
        assert any("next_steps" in w for w in brief["schema_repair_warnings"])

    def test_evidence_gaps_coerces_non_str_element(self):
        brief = normalize_decision_brief({"evidence_gaps": [99]})
        assert brief["evidence_gaps"] == ["99"]
        assert any("evidence_gaps" in w for w in brief["schema_repair_warnings"])


class TestRenderAfterNormalization:
    """正規化した brief がレンダラーで AttributeError を起こさないことを検証する。"""

    def test_render_does_not_crash_on_scalar_list_fields(self):
        raw = {
            "key_reasons": "文字列の根拠",
            "guardrails": ["前提テキスト"],
            "deal_breakers": ["リスクテキスト"],
            "critical_unknowns": ["未知テキスト"],
            "next_decisions": ["決定テキスト"],
            "recommended_actions": ["アクションテキスト"],
            "evidence_gaps": [42],
        }
        brief = normalize_decision_brief(raw)
        # 正規化前は item.get(...) で AttributeError になる形。正規化後は例外を出さない。
        md = render_decision_brief_markdown(brief)
        assert "文字列の根拠" in md
        assert "前提テキスト" in md
        assert "アクションテキスト" in md

    def test_render_does_not_crash_on_scalar_scorecard_and_highlights(self):
        raw = {
            "decision_scorecard": ["スコア項目"],
            "conversation_highlights": {
                "summary": "議論まとめ",
                "consensus": ["合意テキスト"],
                "key_quotes": ["引用テキスト"],
            },
        }
        brief = normalize_decision_brief(raw)
        md = render_decision_brief_markdown(brief)
        assert "スコア項目" in md
        assert "合意テキスト" in md
        assert "引用テキスト" in md


class TestScalarFieldCoercion:
    """スカラフィールドの型強制・NaN/bool ガードを検証する。"""

    def test_recommendation_non_str_coerced(self):
        brief = normalize_decision_brief({"recommendation": 123})
        assert brief["recommendation"] == "123"
        assert any("recommendation" in w for w in brief["schema_repair_warnings"])

    def test_bool_agreement_score_defaults(self):
        # bool は int のサブクラスだが 0/1 の合意度として扱わず 0.5 に落とす
        brief = normalize_decision_brief({"agreement_score": True})
        assert brief["agreement_score"] == 0.5
        assert any("agreement_score" in w for w in brief["schema_repair_warnings"])

    def test_nan_agreement_score_defaults(self):
        brief = normalize_decision_brief({"agreement_score": float("nan")})
        assert brief["agreement_score"] == 0.5
        assert any("agreement_score" in w for w in brief["schema_repair_warnings"])

    def test_inf_agreement_score_defaults(self):
        brief = normalize_decision_brief({"agreement_score": float("inf")})
        assert brief["agreement_score"] == 0.5
        assert any("agreement_score" in w for w in brief["schema_repair_warnings"])

    def test_none_element_in_str_list_becomes_empty(self):
        brief = normalize_decision_brief({"next_steps": [None, "x"]})
        assert brief["next_steps"] == ["", "x"]

    def test_merges_existing_repair_warnings(self):
        brief = normalize_decision_brief(
            {"schema_repair_warnings": ["既存の警告"], "agreement_score": "high"}
        )
        assert "既存の警告" in brief["schema_repair_warnings"]
        assert any("agreement_score" in w for w in brief["schema_repair_warnings"])


class TestNestedNormalization:
    """time_horizon / conversation_highlights / decision_scorecard のネスト正規化。"""

    def test_time_horizon_nested_non_dict_wrapped(self):
        brief = normalize_decision_brief({"time_horizon": {"short_term": "3ヶ月で普及"}})
        assert brief["time_horizon"]["short_term"] == {"prediction": "3ヶ月で普及"}
        assert any("time_horizon.short_term" in w for w in brief["schema_repair_warnings"])

    def test_time_horizon_preserves_valid_dict_subvalue(self):
        src = {"time_horizon": {"mid_term": {"period": "1年", "prediction": "普及拡大"}}}
        brief = normalize_decision_brief(src)
        assert brief["time_horizon"]["mid_term"] == {"period": "1年", "prediction": "普及拡大"}
        assert "schema_repair_warnings" not in brief

    def test_time_horizon_non_dict_replaced_with_empty(self):
        brief = normalize_decision_brief({"time_horizon": "3ヶ月後"})
        assert brief["time_horizon"] == {}
        assert any("time_horizon" in w for w in brief["schema_repair_warnings"])

    def test_decision_scorecard_scalar_element_wrapped(self):
        brief = normalize_decision_brief({"decision_scorecard": ["ROI"]})
        assert brief["decision_scorecard"] == [{"label": "ROI"}]
        assert any("decision_scorecard" in w for w in brief["schema_repair_warnings"])

    def test_conversation_highlights_nested_lists_normalized(self):
        raw = {
            "conversation_highlights": {
                "summary": "まとめ",
                "consensus": ["合意テキスト"],
                "conflicts": [{"point": "対立点"}],
                "turning_points": ["転換テキスト"],
                "key_quotes": ["引用テキスト"],
            }
        }
        brief = normalize_decision_brief(raw)
        hl = brief["conversation_highlights"]
        assert hl["consensus"] == [{"point": "合意テキスト"}]
        assert hl["conflicts"] == [{"point": "対立点"}]
        assert hl["turning_points"] == [{"moment": "転換テキスト"}]
        assert hl["key_quotes"] == [{"quote": "引用テキスト"}]
        assert hl["summary"] == "まとめ"

    def test_conversation_highlights_non_dict_left_untouched(self):
        # 非 dict の highlights はレンダラーが isinstance で弾くため素通し
        brief = normalize_decision_brief({"conversation_highlights": [{"quote": "x"}]})
        assert brief["conversation_highlights"] == [{"quote": "x"}]
        assert "schema_repair_warnings" not in brief
