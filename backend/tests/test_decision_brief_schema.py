"""Decision Brief の正規化（スキーマ検証・デフォルト充填）テスト"""

from src.app.services.decision_brief_schema import normalize_decision_brief


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
