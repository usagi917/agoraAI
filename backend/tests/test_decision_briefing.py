from src.app.services.decision_briefing import (
    build_pm_board_decision_brief,
    build_single_decision_brief,
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

    markdown = render_decision_brief_markdown(brief)

    assert brief["decision_summary"]
    assert brief["recommended_actions"][0]["action"] == "重点顧客の需要検証を行う"
    assert "## Decision Memo" in markdown
    assert "### 主な判断根拠" in markdown
    assert "### 推奨アクション" in markdown
