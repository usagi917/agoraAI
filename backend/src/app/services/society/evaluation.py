"""評価スキャフォールド: Society シミュレーションの品質評価メトリクス"""

import logging
import math
from collections import Counter
from typing import Any

from src.app.services.society.age_utils import age_bracket_4 as _age_bracket

try:
    from scipy.stats import chisquare as _scipy_chisquare
    from scipy.stats import chi2_contingency as _scipy_chi2_contingency
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False
    _scipy_chi2_contingency = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def diversity_index(responses: list[dict]) -> float:
    """Shannon entropy ベースの意見多様性指標 (0-1 正規化)。

    スタンスの分布が均等なほど 1 に近づく。
    """
    if not responses:
        return 0.0

    stances = [r.get("stance", "中立") for r in responses]
    counter = Counter(stances)
    total = len(stances)
    n_categories = len(counter)

    if n_categories <= 1:
        return 0.0

    entropy = 0.0
    for count in counter.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)

    # 最大エントロピーで正規化
    max_entropy = math.log2(n_categories)
    return round(entropy / max_entropy, 4) if max_entropy > 0 else 0.0


def internal_consistency(agents: list[dict], responses: list[dict]) -> float:
    """プロフィールと回答の整合性スコア (0-1)。

    例: 保守的なプロフィール（低O, 高C）の住民が「伝統重視」を優先しているか等を検証。
    """
    if not agents or not responses or len(agents) != len(responses):
        return 0.0

    consistent_count = 0
    total = len(agents)

    for agent, resp in zip(agents, responses):
        big_five = agent.get("big_five", {})
        values = agent.get("values", {})
        stance = resp.get("stance", "中立")

        score = 0.0
        checks = 0

        # Check 1: 高 Openness → 革新的スタンスとの整合
        if big_five.get("O", 0.5) > 0.7:
            if stance in ("賛成", "条件付き賛成"):
                score += 1.0
            elif stance == "中立":
                score += 0.5
            checks += 1
        elif big_five.get("O", 0.5) < 0.3:
            if stance in ("反対", "条件付き反対"):
                score += 1.0
            elif stance == "中立":
                score += 0.5
            checks += 1

        # Check 2: 高 Neuroticism → 低 confidence との整合
        if big_five.get("N", 0.5) > 0.7:
            if resp.get("confidence", 0.5) < 0.6:
                score += 1.0
            checks += 1

        # Check 3: 価値観との整合
        if values:
            top_value = max(values, key=values.get) if values else ""
            reason = resp.get("reason", "").lower()
            if top_value and top_value in reason:
                score += 1.0
            checks += 1

        if checks > 0 and score / checks >= 0.5:
            consistent_count += 1

    return round(consistent_count / total, 4) if total > 0 else 0.0


def calibration_score(responses: list[dict]) -> float:
    """回答の信頼度キャリブレーション (0-1)。

    各スタンスの回答者の平均信頼度が、そのスタンスの人数比と整合しているかを測定。
    過信（少数意見なのに高信頼度）にペナルティ。
    """
    if not responses:
        return 0.0

    stance_groups: dict[str, list[float]] = {}
    for r in responses:
        stance = r.get("stance", "中立")
        conf = r.get("confidence", 0.5)
        if stance not in stance_groups:
            stance_groups[stance] = []
        stance_groups[stance].append(conf)

    total = len(responses)
    penalties = []

    for stance, confidences in stance_groups.items():
        proportion = len(confidences) / total
        avg_conf = sum(confidences) / len(confidences)
        # 過信ペナルティ: 少数意見なのに高信頼度
        if proportion < 0.2 and avg_conf > 0.8:
            penalties.append(0.3)
        elif proportion < 0.1 and avg_conf > 0.6:
            penalties.append(0.2)

    penalty = sum(penalties)
    return round(max(0.0, 1.0 - penalty), 4)


def brier_score(responses: list[dict]) -> float | None:
    """Brier Score: 多数派スタンスに対する信頼度キャリブレーション。

    各エージェントの confidence を「自分のスタンスが正しい確率」と解釈し、
    多数派スタンスとの一致を結果として Brier Score を算出する。

    Returns:
        0(完全予測) ~ 1(最悪予測)。低いほど良い。回答が2件未満なら None。
    """
    if not responses or len(responses) < 2:
        return None

    stances = [r.get("stance", "中立") for r in responses]
    counter = Counter(stances)
    majority_stance = counter.most_common(1)[0][0]

    n = len(responses)
    brier_sum = 0.0

    for r in responses:
        confidence = r.get("confidence", 0.5)
        is_majority = 1.0 if r.get("stance", "中立") == majority_stance else 0.0
        brier_sum += (confidence - is_majority) ** 2

    return round(brier_sum / n, 4)


def kl_divergence(
    responses: list[dict],
    baseline: dict[str, float] | None = None,
) -> float | None:
    """KL-divergence: スタンス分布とベースライン分布の乖離度。

    D_KL(P || Q) = Σ P(x) · log₂(P(x) / Q(x))

    P = 観測されたスタンス分布
    Q = ベースライン分布（デフォルト: 均一分布）

    Returns:
        0(完全一致) ~ ∞(大きな乖離)。回答が無ければ None。
    """
    if not responses:
        return None

    stances = [r.get("stance", "中立") for r in responses]
    counter = Counter(stances)
    total = len(stances)
    categories = list(counter.keys())

    if len(categories) <= 1:
        return 0.0

    if baseline is None:
        baseline = {cat: 1.0 / len(categories) for cat in categories}

    kl = 0.0
    for cat in categories:
        p = counter[cat] / total
        q = baseline.get(cat, 1e-10)
        if p > 0 and q > 0:
            kl += p * math.log2(p / q)

    return round(kl, 4)


def _chi2_p_value(observed: list[float], expected: list[float]) -> float:
    """カイ二乗統計量から p 値を計算する（scipy フォールバック付き）。

    Returns:
        p 値 (0.0〜1.0)。期待度数が全て 0 なら 0.0。
    """
    if _SCIPY_AVAILABLE:
        result = _scipy_chisquare(f_obs=observed, f_exp=expected)
        # scipy 1.11+ は namedtuple / object のいずれか
        p = float(result.pvalue)  # type: ignore[union-attr]
        return p

    # scipy がない場合の手動実装（不完全ガンマ関数で近似）
    chi2 = sum(
        (o - e) ** 2 / e
        for o, e in zip(observed, expected)
        if e > 0
    )
    df = len(observed) - 1
    if df <= 0:
        return 1.0

    # 上側確率: 正規近似（Wilson-Hilferty 変換）
    # df が大きい場合に有効な近似
    k = df
    z = ((chi2 / k) ** (1 / 3) - (1 - 2 / (9 * k))) / math.sqrt(2 / (9 * k))
    # 標準正規の右側面積
    p = 0.5 * (1 + math.erf(-z / math.sqrt(2)))
    return max(0.0, min(1.0, p))


def demographic_representativeness(
    agents: list[dict],
    target_marginals: dict,
) -> float:
    """人口統計的代表性をカイ二乗適合度検定で評価する。

    Args:
        agents: エージェントのリスト。各エージェントは demographics.age を持つ。
        target_marginals: ターゲット周辺分布。
            例: {"age_bracket": {"18-29": 0.25, "30-49": 0.25, ...}}

    Returns:
        p 値 (float, 0.0〜1.0)。
        - p > 0.05: 観測分布はターゲットと有意差なし（代表的）
        - p < 0.05: 観測分布はターゲットと有意差あり（非代表的）
        - エージェントまたはターゲットが空の場合: 0.0
    """
    if not agents or not target_marginals:
        return 0.0

    # age_bracket のみを対象にする
    age_dist = target_marginals.get("age_bracket")
    if not age_dist:
        return 0.0

    brackets = list(age_dist.keys())
    if not brackets:
        return 0.0

    # 観測度数を集計
    observed_counts: dict[str, int] = Counter(
        _age_bracket(a.get("demographics", {}).get("age", 0))
        for a in agents
    )

    n = len(agents)
    observed = [observed_counts.get(b, 0) for b in brackets]
    expected = [age_dist[b] * n for b in brackets]

    # 期待度数が全て正であることを確認
    if any(e <= 0 for e in expected):
        return 0.0

    return round(_chi2_p_value(observed, expected), 6)


def response_quality_score(responses: list[dict]) -> float:
    """レスポンス品質スコアを算出する (0-1)。

    各レスポンスを以下の基準で「高品質」と判定:
    - reason の文字数が 100 文字以上

    Args:
        responses: レスポンスのリスト。各レスポンスは reason キーを持つ。

    Returns:
        高品質レスポンスの割合 (0.0〜1.0)。
    """
    if not responses:
        return 0.0

    high_quality_count = 0
    for r in responses:
        reason = r.get("reason", "")
        if len(reason) >= 100:
            high_quality_count += 1

    return round(high_quality_count / len(responses), 4)


def deliberation_depth(meeting_result: dict) -> float:
    """熟議深度スコアを算出する (0-1)。

    以下の3指標の加重平均:
    1. addressed_to 充填率 (weight 0.4): 全発言中、addressed_to が空でないものの割合
    2. belief_update 充填率 (weight 0.4): 全発言中、belief_update が空でないものの割合
    3. argument 発展率 (weight 0.2): 後半ラウンドの平均文字数が前半より長いか

    Args:
        meeting_result: {"rounds": [[{addressed_to, belief_update, argument}, ...], ...]}

    Returns:
        熟議深度スコア (0.0〜1.0)。rounds が空なら 0.0。
    """
    rounds = meeting_result.get("rounds", [])
    if not rounds:
        return 0.0

    all_statements = [stmt for rnd in rounds for stmt in rnd]
    if not all_statements:
        return 0.0

    total = len(all_statements)

    # 指標1: addressed_to 充填率
    addressed_count = sum(
        1 for s in all_statements if s.get("addressed_to", "").strip()
    )
    addressed_rate = addressed_count / total

    # 指標2: belief_update 充填率
    belief_count = sum(
        1 for s in all_statements if s.get("belief_update", "").strip()
    )
    belief_rate = belief_count / total

    # 指標3: argument 発展率
    # ラウンドが2つ以上あれば、前半と後半の平均文字数を比較
    if len(rounds) >= 2:
        mid = len(rounds) // 2
        early_stmts = [s for rnd in rounds[:mid] for s in rnd]
        late_stmts  = [s for rnd in rounds[mid:] for s in rnd]

        def avg_len(stmts: list[dict]) -> float:
            if not stmts:
                return 0.0
            return sum(len(s.get("argument", "")) for s in stmts) / len(stmts)

        early_avg = avg_len(early_stmts)
        late_avg  = avg_len(late_stmts)

        if early_avg == 0 and late_avg == 0:
            growth_rate = 0.0
        elif early_avg == 0:
            growth_rate = 1.0
        else:
            ratio = late_avg / early_avg
            # ratio >= 2.0 → 満点, ratio = 1.0 → 0点, 線形補間
            growth_rate = min(1.0, max(0.0, (ratio - 1.0)))
    else:
        # ラウンドが1つしかない場合は発展率を中間値とする
        growth_rate = 0.5

    score = 0.4 * addressed_rate + 0.4 * belief_rate + 0.2 * growth_rate
    return round(score, 4)


def detect_provider_bias(
    agents: list[dict],
    responses: list[dict],
) -> dict[str, Any]:
    """LLMプロバイダ間のスタンスバイアスを検出する。

    各プロバイダのスタンス分布をカイ二乗独立性検定で比較し、
    プロバイダ間に統計的に有意な偏りがあるかどうかを判定する。

    Args:
        agents: エージェントのリスト。各エージェントは llm_backend キーを持つ。
        responses: レスポンスのリスト。各レスポンスは stance キーを持つ。
                   agents と responses は同じ順序で対応している。

    Returns:
        {
            "bias_detected": bool,  True if p < 0.05
            "p_value": float,       カイ二乗独立性検定の p 値
            "provider_distributions": dict[str, dict[str, float]],
                                    プロバイダ別のスタンス割合分布
        }
    """
    # 空入力や長さ不一致の場合はバイアスなし
    if not agents or not responses or len(agents) != len(responses):
        return {
            "bias_detected": False,
            "p_value": 1.0,
            "provider_distributions": {},
        }

    # プロバイダ別にスタンスカウントを集計
    provider_stance_counts: dict[str, Counter] = {}
    for agent, resp in zip(agents, responses):
        provider = agent.get("llm_backend", "unknown")
        stance = resp.get("stance", "中立")
        if provider not in provider_stance_counts:
            provider_stance_counts[provider] = Counter()
        provider_stance_counts[provider][stance] += 1

    # プロバイダが1種類以下なら比較不能
    if len(provider_stance_counts) < 2:
        # provider_distributions は計算しておく
        provider_distributions: dict[str, dict[str, float]] = {}
        for provider, counts in provider_stance_counts.items():
            total = sum(counts.values())
            provider_distributions[provider] = {
                stance: count / total for stance, count in counts.items()
            }
        return {
            "bias_detected": False,
            "p_value": 1.0,
            "provider_distributions": provider_distributions,
        }

    # 全スタンスカテゴリを収集
    all_stances = sorted(
        {stance for counts in provider_stance_counts.values() for stance in counts}
    )
    providers = sorted(provider_stance_counts.keys())

    # プロバイダ別分布（割合）を構築
    provider_distributions = {}
    for provider in providers:
        counts = provider_stance_counts[provider]
        total = sum(counts.values())
        provider_distributions[provider] = {
            stance: counts.get(stance, 0) / total for stance in all_stances
        }

    # 分割表（contingency table）を構築: rows=providers, cols=stances
    contingency_table = [
        [provider_stance_counts[provider].get(stance, 0) for stance in all_stances]
        for provider in providers
    ]

    # カイ二乗独立性検定
    p_value = _chi2_contingency_p_value(contingency_table)

    return {
        "bias_detected": p_value < 0.05,
        "p_value": p_value,
        "provider_distributions": provider_distributions,
    }


def _chi2_contingency_p_value(table: list[list[int]]) -> float:
    """分割表のカイ二乗独立性検定を行い p 値を返す。

    Args:
        table: 分割表（rows=グループ, cols=カテゴリ）

    Returns:
        p 値 (0.0〜1.0)。検定不能な場合は 1.0。
    """
    if _SCIPY_AVAILABLE and _scipy_chi2_contingency is not None:
        try:
            result = _scipy_chi2_contingency(table)
            return float(result.pvalue)
        except Exception:
            return 1.0

    # scipy なしの手動実装
    n_rows = len(table)
    n_cols = len(table[0]) if table else 0
    if n_rows < 2 or n_cols < 2:
        return 1.0

    # 行・列の周辺合計
    row_totals = [sum(row) for row in table]
    col_totals = [sum(table[r][c] for r in range(n_rows)) for c in range(n_cols)]
    grand_total = sum(row_totals)
    if grand_total == 0:
        return 1.0

    # カイ二乗統計量
    chi2 = 0.0
    for r in range(n_rows):
        for c in range(n_cols):
            expected = row_totals[r] * col_totals[c] / grand_total
            if expected > 0:
                chi2 += (table[r][c] - expected) ** 2 / expected

    df = (n_rows - 1) * (n_cols - 1)
    if df <= 0:
        return 1.0

    # Wilson-Hilferty 変換で正規近似
    k = df
    if chi2 / k <= 0:
        return 1.0
    z = ((chi2 / k) ** (1 / 3) - (1 - 2 / (9 * k))) / math.sqrt(2 / (9 * k))
    p = 0.5 * (1 + math.erf(-z / math.sqrt(2)))
    return float(max(0.0, min(1.0, p)))


async def evaluate_society_simulation(
    agents: list[dict],
    responses: list[dict],
    *,
    target_marginals: dict | None = None,
    meeting_result: dict | None = None,
) -> list[dict[str, Any]]:
    """Society シミュレーションの評価メトリクスを計算する。

    Returns:
        メトリクスのリスト [{metric_name, score, details, baseline_type, baseline_score}]
    """
    metrics = []

    # Diversity Index
    div_score = diversity_index(responses)
    metrics.append({
        "metric_name": "diversity",
        "score": div_score,
        "details": {"method": "shannon_entropy_normalized"},
        "baseline_type": None,
        "baseline_score": None,
    })

    # Internal Consistency
    con_score = internal_consistency(agents, responses)
    metrics.append({
        "metric_name": "consistency",
        "score": con_score,
        "details": {"method": "profile_response_alignment"},
        "baseline_type": None,
        "baseline_score": None,
    })

    # Calibration
    cal_score = calibration_score(responses)
    metrics.append({
        "metric_name": "calibration",
        "score": cal_score,
        "details": {"method": "overconfidence_penalty"},
        "baseline_type": None,
        "baseline_score": None,
    })

    # Brier Score
    brier = brier_score(responses)
    if brier is not None:
        metrics.append({
            "metric_name": "brier_score",
            "score": brier,
            "details": {"method": "majority_calibration"},
            "baseline_type": None,
            "baseline_score": None,
        })

    # KL Divergence
    kl = kl_divergence(responses)
    if kl is not None:
        metrics.append({
            "metric_name": "kl_divergence",
            "score": kl,
            "details": {"method": "uniform_baseline"},
            "baseline_type": "uniform",
            "baseline_score": 0.0,
        })

    # Demographic Representativeness (optional: requires target_marginals)
    if target_marginals:
        rep_score = demographic_representativeness(agents, target_marginals)
        metrics.append({
            "metric_name": "demographic_representativeness",
            "score": rep_score,
            "details": {"method": "chi_square_goodness_of_fit"},
            "baseline_type": None,
            "baseline_score": None,
        })

    # Response Quality Score
    rq_score = response_quality_score(responses)
    metrics.append({
        "metric_name": "response_quality",
        "score": rq_score,
        "details": {"method": "reason_length_threshold_100chars"},
        "baseline_type": None,
        "baseline_score": None,
    })

    # Deliberation Depth Score (optional: requires meeting_result)
    if meeting_result is not None:
        dd_score = deliberation_depth(meeting_result)
        metrics.append({
            "metric_name": "deliberation_depth",
            "score": dd_score,
            "details": {"method": "addressed_to_belief_update_argument_growth"},
            "baseline_type": None,
            "baseline_score": None,
        })

    logger.info("Evaluation complete: %s", {m["metric_name"]: m["score"] for m in metrics})
    return metrics
