"""評価結果の集計・統計分析スクリプト

使い方:
    uv run python experiments/swarm_validation/aggregate_results.py
"""

import json
import math
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
EVAL_DIR = SCRIPT_DIR / "evaluations"
OUTPUT_PATH = SCRIPT_DIR / "analysis_report.json"

DIMENSIONS = ["depth", "breadth", "actionability", "risk", "overall"]


def load_evaluations() -> list[dict]:
    """evaluations/ 内の全JSONファイルを読み込む。"""
    evals = []
    if not EVAL_DIR.exists():
        print(f"評価ディレクトリが見つかりません: {EVAL_DIR}")
        return evals
    for f in sorted(EVAL_DIR.glob("eval_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            evals.append(data)
            print(f"  読み込み: {f.name} (評価者: {data.get('evaluator_name', '?')})")
        except (json.JSONDecodeError, OSError) as e:
            print(f"  スキップ: {f.name} ({e})")
    return evals


def deanonymize(evaluations: list[dict]) -> list[dict]:
    """A/Bの割り当てを解除し、single/swarmに変換。"""
    records = []
    for ev in evaluations:
        assignment_map = ev.get("assignment_map", {})
        evaluator = ev.get("evaluator_name", "unknown")
        for r in ev.get("ratings", []):
            tc_id = r["test_case_id"]
            mapping = assignment_map.get(tc_id, {})
            if not mapping:
                continue

            # スコアをsingle/swarmに振り分け
            single_scores = {}
            swarm_scores = {}
            for dim in DIMENSIONS:
                a_val = r.get("a_scores", {}).get(dim)
                b_val = r.get("b_scores", {}).get(dim)
                if mapping.get("A") == "single":
                    single_scores[dim] = a_val
                    swarm_scores[dim] = b_val
                else:
                    single_scores[dim] = b_val
                    swarm_scores[dim] = a_val

            # 勝者をsingle/swarmに変換
            winner_raw = r.get("winner")
            if winner_raw == "tie":
                winner = "tie"
            elif winner_raw in ("A", "B"):
                winner = mapping.get(winner_raw, winner_raw)
            else:
                winner = None

            records.append({
                "evaluator": evaluator,
                "test_case_id": tc_id,
                "domain": r.get("domain", ""),
                "winner": winner,
                "single_scores": single_scores,
                "swarm_scores": swarm_scores,
            })
    return records


def sign_test(differences: list[float]) -> dict:
    """符号検定（小サンプル向けノンパラメトリック検定）。"""
    positives = sum(1 for d in differences if d > 0)
    negatives = sum(1 for d in differences if d < 0)
    ties = sum(1 for d in differences if d == 0)
    n = positives + negatives  # ties excluded

    if n == 0:
        return {"p_value": 1.0, "n": 0, "positives": 0, "negatives": 0, "ties": ties}

    # 二項検定の正確p値（両側）
    # P(X >= max(pos, neg)) under H0: p=0.5
    k = max(positives, negatives)
    p_value = 0.0
    for i in range(k, n + 1):
        p_value += math.comb(n, i) * (0.5 ** n)
    p_value *= 2  # 両側
    p_value = min(p_value, 1.0)

    return {
        "p_value": round(p_value, 4),
        "n": n,
        "positives": positives,
        "negatives": negatives,
        "ties": ties,
    }


def compute_stats(records: list[dict]) -> dict:
    """全統計を計算。"""

    # 1. Win rate
    wins = {"single": 0, "swarm": 0, "tie": 0, "no_answer": 0}
    for r in records:
        w = r.get("winner")
        if w in wins:
            wins[w] += 1
        else:
            wins["no_answer"] += 1
    total_judged = wins["single"] + wins["swarm"] + wins["tie"]

    win_rate = {
        "swarm_win": wins["swarm"],
        "single_win": wins["single"],
        "tie": wins["tie"],
        "total": total_judged,
        "swarm_win_rate": round(wins["swarm"] / total_judged, 3) if total_judged else 0,
        "single_win_rate": round(wins["single"] / total_judged, 3) if total_judged else 0,
    }

    # 2. Per-dimension stats
    dim_stats = {}
    for dim in DIMENSIONS:
        single_vals = [r["single_scores"].get(dim) for r in records if r["single_scores"].get(dim) is not None]
        swarm_vals = [r["swarm_scores"].get(dim) for r in records if r["swarm_scores"].get(dim) is not None]

        single_mean = sum(single_vals) / len(single_vals) if single_vals else 0
        swarm_mean = sum(swarm_vals) / len(swarm_vals) if swarm_vals else 0

        # Paired differences (swarm - single)
        diffs = []
        for r in records:
            s = r["single_scores"].get(dim)
            w = r["swarm_scores"].get(dim)
            if s is not None and w is not None:
                diffs.append(w - s)

        test_result = sign_test(diffs) if diffs else None

        dim_stats[dim] = {
            "single_mean": round(single_mean, 2),
            "swarm_mean": round(swarm_mean, 2),
            "diff": round(swarm_mean - single_mean, 2),
            "n_pairs": len(diffs),
            "sign_test": test_result,
        }

    # 3. Per-domain breakdown
    domain_stats = defaultdict(lambda: {"single": 0, "swarm": 0, "tie": 0})
    for r in records:
        d = r.get("domain", "unknown")
        w = r.get("winner")
        if w in ("single", "swarm", "tie"):
            domain_stats[d][w] += 1

    # 4. Per-evaluator stats (inter-rater)
    evaluator_winners = defaultdict(list)
    for r in records:
        evaluator_winners[r["evaluator"]].append(r.get("winner"))

    return {
        "win_rate": win_rate,
        "dimension_stats": dim_stats,
        "domain_breakdown": dict(domain_stats),
        "evaluator_count": len(evaluator_winners),
        "evaluators": list(evaluator_winners.keys()),
        "total_ratings": len(records),
    }


def print_report(stats: dict) -> None:
    """レポートを標準出力に表示。"""
    print("\n" + "=" * 60)
    print("  Single vs Swarm 品質比較 - 分析レポート")
    print("=" * 60)

    wr = stats["win_rate"]
    print(f"\n■ 勝敗 (N={wr['total']})")
    print(f"  Swarm勝利: {wr['swarm_win']} ({wr['swarm_win_rate']*100:.1f}%)")
    print(f"  Single勝利: {wr['single_win']} ({wr['single_win_rate']*100:.1f}%)")
    print(f"  引き分け: {wr['tie']}")

    print(f"\n■ 次元別スコア平均 (1-5)")
    print(f"  {'次元':<16} {'Single':>8} {'Swarm':>8} {'差分':>8} {'p値':>8} {'有意':>6}")
    print(f"  {'-'*58}")
    for dim in DIMENSIONS:
        ds = stats["dimension_stats"][dim]
        st = ds.get("sign_test")
        p = st["p_value"] if st else "-"
        sig = "**" if st and st["p_value"] < 0.05 else ("*" if st and st["p_value"] < 0.1 else "")
        p_str = f"{p:.3f}" if isinstance(p, float) else p
        dim_labels = {
            "depth": "分析の深さ",
            "breadth": "視点の多様性",
            "actionability": "実行可能性",
            "risk": "リスク特定",
            "overall": "総合品質",
        }
        print(f"  {dim_labels[dim]:<14} {ds['single_mean']:>8.2f} {ds['swarm_mean']:>8.2f} {ds['diff']:>+8.2f} {p_str:>8} {sig:>6}")

    print(f"\n■ ドメイン別勝敗")
    for domain, dw in stats.get("domain_breakdown", {}).items():
        print(f"  {domain:<16} Swarm:{dw['swarm']} Single:{dw['single']} Tie:{dw['tie']}")

    print(f"\n■ 評価者: {stats['evaluator_count']}名 ({', '.join(stats['evaluators'])})")
    print(f"  評価件数: {stats['total_ratings']}")

    # Verdict
    print(f"\n{'='*60}")
    swarm_wr = wr["swarm_win_rate"]
    overall = stats["dimension_stats"]["overall"]
    if swarm_wr > 0.6 and overall["diff"] > 0:
        print("  判定: Swarmモードは品質向上に寄与している")
    elif swarm_wr < 0.4 and overall["diff"] < 0:
        print("  判定: Swarmモードは品質向上に寄与していない")
    else:
        print("  判定: 結果は決定的でない（追加データが必要）")
    print("=" * 60)


def main():
    print("評価結果の集計を開始...")
    evaluations = load_evaluations()
    if not evaluations:
        print("評価ファイルが見つかりません。")
        print(f"evaluation.html でエクスポートしたJSONを {EVAL_DIR}/ に配置してください。")
        return

    records = deanonymize(evaluations)
    if not records:
        print("有効な評価レコードがありません。")
        return

    stats = compute_stats(records)
    print_report(stats)

    # Save
    OUTPUT_PATH.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n詳細レポート: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
