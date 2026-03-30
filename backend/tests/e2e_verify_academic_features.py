"""E2E検証: 学術レベル機能が正しく統合されているか確認する。

DB・LLMをモックし、orchestratorの全フェーズを通して
信頼区間・メソドロジー・グラウンディング・DQI・provenanceが出力に含まれるか検証する。
"""

import asyncio
import json
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

# --- パス設定 ---
sys.path.insert(0, "src")

from src.app.services.society.population_generator import generate_population
from src.app.services.society.agent_selector import select_agents
from src.app.services.society.activation_layer import run_activation, _aggregate_opinions
from src.app.services.society.data_grounding import load_grounding_facts, distribute_facts_to_agents
from src.app.services.society.statistical_inference import (
    compute_poststratification_weights,
    weighted_stance_distribution,
    bootstrap_confidence_intervals,
    effective_sample_size,
    load_target_marginals,
)
from src.app.services.society.narrative_generator import generate_narrative
from src.app.services.society.provenance import build_provenance
from src.app.services.society.deliberation_quality import compute_dqi, measure_opinion_change
from src.app.services.society.calibration import brier_external, calibration_grade
from src.app.services.society.evaluation import detect_provider_bias
from src.app.services.society.output_validator import (
    validate_activation_meeting_consistency,
    validate_response_quality,
    validate_minority_preservation,
)


async def main():
    print("=" * 70)
    print("E2E 検証: 学術レベル機能統合テスト")
    print("=" * 70)

    theme = "日本における少子化対策として、児童手当の大幅拡充は有効か"
    checks_passed = 0
    checks_total = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal checks_passed, checks_total
        checks_total += 1
        if condition:
            checks_passed += 1
            print(f"  [PASS] {name}")
        else:
            print(f"  [FAIL] {name} — {detail}")

    # === 1. 人口生成 + エージェント選出 ===
    print("\n--- Phase 1: 人口生成 + 選出 ---")
    agents = await generate_population("e2e-test", count=200, seed=42)
    check("人口生成 200人", len(agents) == 200)

    selected = await select_agents(agents, theme, target_count=50, min_count=20, max_count=100)
    check("エージェント選出", len(selected) >= 20)

    # 人口統計的多様性チェック
    age_brackets = set()
    regions = set()
    genders = set()
    for a in selected:
        age = a["demographics"]["age"]
        if age < 30: age_brackets.add("18-29")
        elif age < 50: age_brackets.add("30-49")
        elif age < 70: age_brackets.add("50-69")
        else: age_brackets.add("70+")
        regions.add(a["demographics"]["region"])
        genders.add(a["demographics"]["gender"])

    check("年齢帯 3+ カバー", len(age_brackets) >= 3, f"got {len(age_brackets)}")
    check("地域 3+ カバー", len(regions) >= 3, f"got {len(regions)}")
    check("男女両方含む", len(genders) >= 2, f"got {genders}")

    # === 2. グラウンディング ===
    print("\n--- Phase 2: グラウンディング ---")
    facts = load_grounding_facts(theme)
    check("グラウンディング事実取得", len(facts) > 0, f"got {len(facts)}")

    if facts:
        check("事実に出典あり", all(f.get("source") for f in facts))
        agent_facts = distribute_facts_to_agents(selected, facts, max_per_agent=3)
        check("事実配布完了", len(agent_facts) > 0)
        check("事実は max_per_agent 以下", all(len(v) <= 3 for v in agent_facts.values()))

    # === 3. 統計的推論 ===
    print("\n--- Phase 3: 統計的推論 ---")
    # モックレスポンスを生成
    import random
    random.seed(42)
    stances = ["賛成", "反対", "条件付き賛成", "条件付き反対", "中立"]
    mock_responses = []
    for i, a in enumerate(selected):
        stance = random.choices(stances, weights=[0.35, 0.25, 0.20, 0.10, 0.10])[0]
        mock_responses.append({
            "stance": stance,
            "confidence": round(random.uniform(0.3, 0.95), 2),
            "reason": f"エージェント{i}の理由。{a['demographics']['occupation']}として、"
                      f"{a['demographics']['region']}での生活実感に基づくと、この政策は" + "あ" * 100,
            "concern": f"懸念事項{i}",
            "priority": f"優先事項{i}",
        })

    aggregation = _aggregate_opinions(mock_responses, agents=selected)
    check("ウェイト付き分布あり", aggregation.get("weighting_applied", False))
    check("信頼区間あり", "confidence_intervals" in aggregation and len(aggregation["confidence_intervals"]) > 0)
    check("有効標本数あり", "effective_sample_size" in aggregation and aggregation["effective_sample_size"] > 0,
          f"n_eff={aggregation.get('effective_sample_size')}")
    check("誤差幅あり", "margin_of_error" in aggregation and aggregation["margin_of_error"] > 0)
    check("生分布保持", "stance_distribution_raw" in aggregation)
    check("design_effect あり", "design_effect" in aggregation)

    # === 4. 出力検証 ===
    print("\n--- Phase 4: 出力検証 ---")
    synthesis = {
        "recommendations": ["児童手当の段階的拡充を推奨"],
        "overall_assessment": "全体として肯定的だが、財源確保が課題",
        "consensus_points": ["少子化対策の必要性は合意"],
        "disagreement_points": [{"topic": "財源", "positions": []}],
    }

    consistency = validate_activation_meeting_consistency(aggregation, synthesis)
    check("一貫性検証が動作", "status" in consistency)

    quality = validate_response_quality(mock_responses)
    check("レスポンス品質率", "response_quality_rate" in quality)
    check("品質率が0-1", 0 <= quality["response_quality_rate"] <= 1)

    narrative_data = {
        "controversy_areas": [
            {"point": "賛成派と反対派の対立", "positions": ["賛成", "反対"]},
        ],
    }
    minority = validate_minority_preservation(aggregation, narrative_data)
    check("少数派保全チェック動作", "status" in minority)

    # === 5. 熟議品質 (DQI) ===
    print("\n--- Phase 5: 熟議品質 (DQI) ---")
    mock_rounds = [
        [
            {"participant": "田中", "position": "賛成", "argument": "子育て世帯の負担軽減は急務です。" * 10,
             "evidence": "OECD調査で日本の児童手当はGDP比0.7%", "addressed_to": "", "belief_update": "",
             "concerns": ["財源"], "questions_to_others": ["反対派の代替案は？"]},
            {"participant": "鈴木", "position": "反対", "argument": "バラマキでは根本解決にならない。" * 10,
             "evidence": "", "addressed_to": "", "belief_update": "",
             "concerns": ["効果なし"], "questions_to_others": []},
        ],
        [
            {"participant": "田中", "position": "賛成", "argument": "鈴木さんの指摘は理解できますが、北欧の事例では..." * 5,
             "evidence": "フィンランドの出生率回復データ", "addressed_to": "鈴木", "belief_update": "",
             "concerns": [], "questions_to_others": []},
            {"participant": "鈴木", "position": "条件付き反対", "argument": "田中さんのデータは一理ある。しかし日本の文脈では..." * 5,
             "evidence": "", "addressed_to": "田中", "belief_update": "北欧の事例は参考になる",
             "concerns": [], "questions_to_others": []},
        ],
        [
            {"participant": "田中", "position": "賛成", "argument": "総合的に見て段階的拡充が妥当。" * 5,
             "evidence": "", "addressed_to": "", "belief_update": "",
             "concerns": [], "questions_to_others": []},
            {"participant": "鈴木", "position": "条件付き賛成", "argument": "効果検証をセットにするなら賛成に転じる。" * 5,
             "evidence": "", "addressed_to": "", "belief_update": "議論を通じて条件付きで賛成に",
             "concerns": [], "questions_to_others": []},
        ],
    ]

    dqi = compute_dqi(mock_rounds)
    check("DQI 5次元あり", len(dqi.get("dimensions", {})) == 5, f"got {len(dqi.get('dimensions', {}))}")
    check("DQI overall 0-1", 0 <= dqi.get("overall_dqi", -1) <= 1)

    opinion = measure_opinion_change(mock_rounds)
    check("意見変化検出", opinion.get("change_rate", 0) > 0, f"rate={opinion.get('change_rate')}")
    check("Fishkin比較あり", "fishkin_comparison" in opinion and len(opinion["fishkin_comparison"]) > 0)

    # === 6. Provenance ===
    print("\n--- Phase 6: Provenance ---")
    provenance = build_provenance(
        population_size=200,
        selected_count=len(selected),
        effective_sample_size=aggregation.get("effective_sample_size", 50),
        activation_params={"temperature": 0.5},
        meeting_params={"num_rounds": 3, "participants": 10},
        quality_metrics={"diversity_index": 0.82, "dqi_overall": dqi["overall_dqi"]},
        seed=42,
    )
    check("methodology あり", "methodology" in provenance)
    check("Fishkin 引用", "Fishkin" in str(provenance["methodology"]))
    check("data_sources あり", len(provenance.get("data_sources", [])) > 0)
    check("parameters 正確", provenance["parameters"]["population_size"] == 200)
    check("limitations あり", len(provenance.get("limitations", [])) > 0)
    check("git hash あり", provenance["reproducibility"]["code_version"] != "")
    check("timestamp あり", "timestamp" in provenance["reproducibility"])

    # === 7. メソドロジーセクション ===
    print("\n--- Phase 7: メソドロジーセクション ---")
    narrative = generate_narrative(
        agents=selected,
        responses=mock_responses,
        synthesis=synthesis,
        aggregation=aggregation,
        demographic_analysis={},
        provenance=provenance,
    )
    check("methodology_section あり", narrative.get("methodology_section") is not None)
    if narrative.get("methodology_section"):
        ms = narrative["methodology_section"]
        check("有効標本数記載", "有効標本数" in ms or "effective_sample" in ms.lower())
        check("信頼区間記載", "信頼区間" in ms)
        check("Fishkin記載", "Fishkin" in ms)
        check("制約事項記載", "制約" in ms or "限界" in ms)

    # === 8. キャリブレーション ===
    print("\n--- Phase 8: キャリブレーション ---")
    brier = brier_external({"賛成": 0.6, "反対": 0.3, "中立": 0.1}, "賛成")
    check("Brier スコア算出", 0 <= brier <= 2, f"brier={brier}")

    grade = calibration_grade(0.03)
    check("キャリブレーショングレード", grade == "well_calibrated", f"got {grade}")

    # === 9. プロバイダバイアス検出 ===
    print("\n--- Phase 9: プロバイダバイアス ---")
    bias = detect_provider_bias(selected, mock_responses)
    check("バイアス検出が動作", "bias_detected" in bias)
    check("プロバイダ分布あり", "provider_distributions" in bias)

    # === 結果 ===
    print("\n" + "=" * 70)
    print(f"結果: {checks_passed}/{checks_total} チェック通過")
    if checks_passed == checks_total:
        print("全チェック PASS — 学術レベル機能の統合が正常に動作しています")
    else:
        print(f"FAIL: {checks_total - checks_passed} 件のチェックが失敗")
    print("=" * 70)

    return checks_passed == checks_total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
