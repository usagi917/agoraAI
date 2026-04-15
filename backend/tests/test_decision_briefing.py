from src.app.services.decision_briefing import (
    build_conversation_highlights,
    build_pm_board_decision_brief,
    build_single_decision_brief,
    enrich_decision_brief,
    render_decision_brief_markdown,
)


def test_build_pm_board_decision_brief_contains_decision_fields():
    pm_result = {
        "overall_confidence": 0.64,
        "key_decision_points": ["価格仮説の検証結果", "パイロットの有料転換率"],
        "contradictions": [
            {
                "issue": "AI機能を初期スコープに含めるかで見解が割れている",
                "resolution": "MVP後に回す",
            },
        ],
        "sections": {
            "core_question": "中堅建設会社向けSaaSは成立するか",
            "assumptions": [
                {
                    "assumption": "月額3万円の価格帯が受容される",
                    "confidence": 0.55,
                    "impact_if_wrong": "ユニットエコノミクスが崩れる",
                },
            ],
            "uncertainties": [
                {
                    "uncertainty": "紙文化からの移行速度",
                    "impact": "採用速度に影響",
                    "validation_method": "パイロット検証",
                },
            ],
            "risks": [
                {
                    "risk": "競合の本格参入",
                    "impact": "差別化が薄れる",
                    "mitigation": "中小特化で差別化する",
                },
            ],
            "winning_hypothesis": {
                "if_true": "現場監督が5分以内で日報入力できる",
                "then_do": "モバイルSaaSとして提供する",
                "to_achieve": "12ヶ月で ARR 1億円",
                "confidence": 0.58,
            },
            "customer_validation_plan": {
                "timeline": "4週間",
                "target_segments": ["従業員50-200名の中堅建設会社"],
                "success_criteria": "60%以上が有料でも使いたいと回答",
            },
            "market_view": {
                "market_size": "3,000億円",
                "growth_rate": "年率12%",
                "key_players": [{"name": "ANDPAD", "position": "国内リーダー"}],
            },
            "gtm_hypothesis": {
                "target_customer": "現場監督と工事部長",
            },
            "plan_30_60_90": {
                "day_30": {"goals": ["顧客インタビュー10件完了"]},
                "day_60": {"goals": ["MVP開発完了"]},
                "day_90": {"goals": ["有料転換2社以上"]},
            },
            "top_5_actions": [
                {
                    "action": "価格ヒアリングを実施する",
                    "owner": "CEO",
                    "deadline": "2週間",
                    "decision_impact": "価格仮説の成立可否が分かる",
                    "additional_info_needed": "競合の実売価格",
                    "confidence": 0.78,
                },
            ],
        },
    }

    brief = build_pm_board_decision_brief(
        prompt_text="建設SaaSの事業化を検討する",
        pm_result=pm_result,
        scenarios=[{"description": "価格障壁で導入が遅れる", "scenario_score": 0.68}],
    )

    assert brief["decision_summary"]
    assert brief["guardrails"][0]["condition"] == "月額3万円の価格帯が受容される"
    assert brief["critical_unknowns"][0]["question"] == "紙文化からの移行速度"
    assert brief["recommended_actions"][0]["action"] == "価格ヒアリングを実施する"
    assert "価格仮説" in brief["next_decisions"][0]["decision"]


def test_build_single_decision_brief_renders_markdown_memo():
    brief = build_single_decision_brief(
        prompt_text="EV市場への参入を検討する",
        report_content="市場成長は強いが、供給網リスクが残るため条件付きで進めるべき。",
        sections={
            "executive_summary": "市場成長は強いが、供給網リスクが残るため条件付きで進めるべき。",
            "recommended_actions": "重点顧客の需要検証を行う。供給網の代替先を洗い出す。",
            "risks": "供給網が逼迫すると参入時期が遅れる。",
            "uncertainty": "需要の立ち上がり速度が未確定。",
        },
        quality={"status": "verified", "trust_level": "high_trust"},
    )
    brief = enrich_decision_brief(
        brief,
        quality={
            "status": "verified",
            "trust_level": "high_trust",
            "evidence_mode": "strict",
            "document_refs_count": 2,
            "prompt_refs_count": 1,
        },
        run_config={"evidence_mode": "strict", "trust_mode": "strict"},
        verification={"status": "passed", "score": 0.86, "issues": [], "warnings": []},
        evidence_refs=[{"label": "doc-1"}, {"label": "doc-2"}],
    )

    markdown = render_decision_brief_markdown(brief)

    assert brief["decision_summary"]
    assert brief["recommended_actions"][0]["action"] == "重点顧客の需要検証を行う"
    assert brief["decision_scorecard"][0]["label"] == "実行条件"
    assert brief["followup_prompts"]
    assert "## Decision Memo" in markdown
    assert "### 主な判断根拠" in markdown
    assert "### 推奨アクション" in markdown
    assert "### 判断の基準" in markdown
    assert "### 深掘りに使う follow-up" in markdown


# ---------------------------------------------------------------------------
# build_conversation_highlights tests
# ---------------------------------------------------------------------------

_COUNCIL_SYNTHESIS = {
    "consensus_points": [
        "月額3万円の価格帯は中堅建設には受容されやすい",
        "パイロット参加企業5社の継続意向が強い",
        "モバイルファーストが現場ニーズに合っている",
        "競合ANDPADより安価なポジショニングが有効",
    ],
    "disagreement_points": [
        {"topic": "AI機能の初期スコープ", "impact": "開発コストと優先度に影響"},
        {"topic": "販路の直販vs代理店", "impact": "立ち上がり速度に影響"},
        {"topic": "海外展開タイミング", "impact": "リソース分散リスクがある"},
        {"topic": "フリーミアム採用可否", "impact": "ARRモデルに影響"},
    ],
    "stance_shifts": [
        {"moment": "パイロット継続率70%が判明した時点", "reason": "当初懐疑的だった委員が支持に転じた"},
        {"moment": "競合の値上げが確認された時点", "reason": "価格優位の根拠が強まった"},
        {"moment": "代理店ネットワーク活用の提案後", "reason": "販路リスクが低下した"},
        {"moment": "MVP完成デモの後", "reason": "UXへの懸念が解消された"},
    ],
    "most_persuasive_argument": {
        "participant": "田中CFO",
        "argument": "パイロット期間で有料転換率が60%を超えた実績があるため、価格受容の仮説は既に実証されている",
    },
    "overall_assessment": "全体として条件付きGoが妥当。初期スコープを絞りつつ早期に有料転換実績を積むべき。課題はAI機能の優先度のみ。",
}

_PM_RESULT = {
    "overall_confidence": 0.68,
    "key_decision_points": ["価格仮説の検証完了", "パイロット有料転換率確認"],
    "contradictions": [
        {"issue": "AI機能を含めるか否かで意見が分かれた", "resolution": "MVP後に回す"},
    ],
    "sections": {
        "core_question": "中堅建設会社向けSaaSの事業化は成立するか",
        "assumptions": [
            {"assumption": "月額3万円が受容される", "confidence": 0.72, "impact_if_wrong": "収益モデルが崩れる"},
            {"assumption": "現場導入ハードルが低い", "confidence": 0.65, "impact_if_wrong": "採用速度が落ちる"},
        ],
        "winning_hypothesis": {
            "if_true": "現場監督が5分で日報入力できる",
            "then_do": "モバイルSaaSとして提供する",
        },
    },
}


def test_build_conversation_highlights_from_council_synthesis():
    result = build_conversation_highlights(
        council_synthesis=_COUNCIL_SYNTHESIS,
        recommendation="条件付きGo",
    )

    assert result is not None
    assert result["source_phase"] == "council"
    assert result["summary"]

    # consensus: up to 3, each has "point" and "impact"
    assert len(result["consensus"]) <= 3
    for item in result["consensus"]:
        assert "point" in item
        assert "impact" in item

    # conflicts: up to 3, each has "point", "status", "impact"
    assert len(result["conflicts"]) <= 3
    for item in result["conflicts"]:
        assert "point" in item
        assert "status" in item
        assert "impact" in item

    # turning_points: up to 3, each has "moment" and "why_it_changed"
    assert len(result["turning_points"]) <= 3
    for item in result["turning_points"]:
        assert "moment" in item
        assert "why_it_changed" in item

    # key_quotes: up to 3, each has "speaker", "quote", "decision_impact"
    assert len(result["key_quotes"]) <= 3
    for item in result["key_quotes"]:
        assert "speaker" in item
        assert "quote" in item
        assert "decision_impact" in item
        # quotes are truncated to 120 chars
        assert len(item["quote"]) <= 120


def test_build_conversation_highlights_from_pm_result_only():
    result = build_conversation_highlights(
        pm_result=_PM_RESULT,
        recommendation="条件付きGo",
    )

    assert result is not None
    assert result["source_phase"] == "meeting"
    # Falls back to pm_result data — at minimum summary is populated
    assert result["summary"]


def test_build_conversation_highlights_returns_none_when_empty():
    result = build_conversation_highlights()
    assert result is None

    result = build_conversation_highlights(
        council_synthesis={},
        pm_result={},
        recommendation="",
    )
    assert result is None


def test_build_conversation_highlights_max_3_per_array():
    """10-item inputs must still produce at most 3 items per array."""
    large_synthesis = {
        "consensus_points": [f"合意点{i}" for i in range(10)],
        "disagreement_points": [{"topic": f"対立点{i}", "impact": f"影響{i}"} for i in range(10)],
        "stance_shifts": [{"moment": f"転換点{i}", "reason": f"理由{i}"} for i in range(10)],
        "most_persuasive_argument": {
            "participant": "スピーカーA",
            "argument": "長い説得力のある主張" * 20,  # > 120 chars
        },
        "overall_assessment": "全体として進めるべき。",
    }
    result = build_conversation_highlights(council_synthesis=large_synthesis)

    assert result is not None
    assert len(result["consensus"]) <= 3
    assert len(result["conflicts"]) <= 3
    assert len(result["turning_points"]) <= 3
    assert len(result["key_quotes"]) <= 3
    # Quotes must be truncated
    for item in result["key_quotes"]:
        assert len(item["quote"]) <= 120


def test_build_pm_board_decision_brief_includes_highlights():
    brief = build_pm_board_decision_brief(
        prompt_text="建設SaaSの事業化を検討する",
        pm_result=_PM_RESULT,
        council_synthesis=_COUNCIL_SYNTHESIS,
    )

    assert "conversation_highlights" in brief
    highlights = brief["conversation_highlights"]
    assert highlights is not None
    assert highlights["source_phase"] == "council"


def test_enrich_decision_brief_preserves_existing_highlights():
    existing_highlights = {
        "summary": "既存のハイライト",
        "consensus": [{"point": "既存合意", "impact": "高"}],
        "conflicts": [],
        "turning_points": [],
        "key_quotes": [],
        "source_phase": "council",
    }
    brief = {
        "recommendation": "Go",
        "decision_summary": "テスト",
        "conversation_highlights": existing_highlights,
    }
    enriched = enrich_decision_brief(
        brief,
        council_synthesis=_COUNCIL_SYNTHESIS,
    )
    # Existing highlights must NOT be overwritten
    assert enriched["conversation_highlights"]["summary"] == "既存のハイライト"


def test_enrich_decision_brief_adds_highlights_when_council_synthesis_present():
    brief = {
        "recommendation": "条件付きGo",
        "decision_summary": "テスト",
    }
    enriched = enrich_decision_brief(
        brief,
        council_synthesis=_COUNCIL_SYNTHESIS,
    )
    assert "conversation_highlights" in enriched
    assert enriched["conversation_highlights"] is not None


def test_render_decision_brief_markdown_includes_highlights():
    highlights = {
        "summary": "全体として条件付きGoが妥当。",
        "consensus": [{"point": "価格受容性が確認された", "impact": "収益モデルが成立"}],
        "conflicts": [{"point": "AI機能スコープ", "status": "unresolved", "impact": "開発優先度に影響"}],
        "turning_points": [{"moment": "継続率70%判明時", "why_it_changed": "懐疑的委員が支持に転じた"}],
        "key_quotes": [{"speaker": "田中CFO", "quote": "有料転換率60%超の実績がある", "decision_impact": "価格仮説を裏付ける"}],
        "source_phase": "council",
    }
    brief = {
        "recommendation": "条件付きGo",
        "decision_summary": "テスト",
        "conversation_highlights": highlights,
    }
    markdown = render_decision_brief_markdown(brief)

    assert "### 議論ハイライト" in markdown
    assert "全体として条件付きGoが妥当" in markdown
    assert "価格受容性が確認された" in markdown
    assert "AI機能スコープ" in markdown
    assert "継続率70%判明時" in markdown
    assert "田中CFO" in markdown


def test_render_decision_brief_markdown_skips_highlights_when_absent():
    brief = {
        "recommendation": "Go",
        "decision_summary": "ハイライトなしのテスト",
    }
    markdown = render_decision_brief_markdown(brief)
    assert "### 議論ハイライト" not in markdown
