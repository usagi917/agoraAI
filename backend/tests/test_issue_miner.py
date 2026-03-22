from src.app.services.society.issue_miner import (
    build_intervention_comparison,
    mine_issue_candidates,
    select_top_issues,
)


def _agent(region: str, occupation: str) -> dict:
    return {
        "demographics": {
            "region": region,
            "occupation": occupation,
        }
    }


def test_mine_issue_candidates_groups_market_topics():
    agents = [
        _agent("関東", "会社員"),
        _agent("関西", "学生"),
        _agent("中部", "自営業"),
        _agent("九州", "会社員"),
    ]
    responses = [
        {
            "stance": "賛成",
            "confidence": 0.8,
            "reason": "価格が高いと導入しづらい",
            "concern": "価格負担",
            "priority": "価格",
        },
        {
            "stance": "反対",
            "confidence": 0.7,
            "reason": "安全性の説明が不足していて不安",
            "concern": "安全リスク",
            "priority": "安全性",
        },
        {
            "stance": "条件付き賛成",
            "confidence": 0.75,
            "reason": "規制に合えば導入したい",
            "concern": "規制対応",
            "priority": "コンプライアンス",
        },
        {
            "stance": "中立",
            "confidence": 0.6,
            "reason": "価格がもう少し下がれば広がる",
            "concern": "価格",
            "priority": "需要",
        },
    ]

    issues = mine_issue_candidates(agents, responses)

    assert issues
    labels = [issue["label"] for issue in issues]
    assert "価格受容性" in labels
    assert "規制対応" in labels
    assert any(issue["selection_score"] > 0 for issue in issues)


def test_select_top_issues_and_build_interventions():
    issues = [
        {
            "issue_id": "issue-1",
            "label": "価格受容性",
            "description": "",
            "population_share": 0.4,
            "controversy_score": 0.5,
            "market_impact_score": 0.9,
            "network_spread_score": 0.7,
            "selection_score": 0.82,
            "supporting_stances": [],
            "sample_reasons": [],
        },
        {
            "issue_id": "issue-2",
            "label": "規制対応",
            "description": "",
            "population_share": 0.3,
            "controversy_score": 0.4,
            "market_impact_score": 0.88,
            "network_spread_score": 0.5,
            "selection_score": 0.74,
            "supporting_stances": [],
            "sample_reasons": [],
        },
    ]
    selected = select_top_issues(issues, limit=1)
    assert [issue["issue_id"] for issue in selected] == ["issue-1"]

    interventions = build_intervention_comparison(
        issues,
        [
            {
                "label": "価格受容性",
                "top_scenarios": [{"description": "価格障壁で導入が遅れる", "scenario_score": 0.72}],
            },
            {
                "label": "規制対応",
                "top_scenarios": [{"description": "制度整合で採用が回復する", "scenario_score": 0.61}],
            },
        ],
    )
    assert interventions
    assert {item["label"] for item in interventions} >= {"価格変更", "規制対応強化"}
    assert all(item["comparison_mode"] == "heuristic" for item in interventions)
