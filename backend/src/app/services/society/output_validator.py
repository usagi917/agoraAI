"""出力バリデーター:

活性化結果と会議結論の整合性、レスポンス品質、少数派意見の保全を検証する。
"""

import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# キーワード定義
# ---------------------------------------------------------------------------

_POSITIVE_KEYWORDS = ["推進", "推奨", "賛成", "Go", "導入", "肯定", "支持"]
_NEGATIVE_KEYWORDS = ["反対", "中止", "見送り", "No-Go", "否定", "撤回", "廃止"]

# 少数派と見なす閾値（この割合未満のスタンスを少数派扱い）
_MINORITY_THRESHOLD = 0.15

# 高品質 reason の最小文字数
_MIN_REASON_LENGTH = 100

# 具体性を示す正規表現パターン
_SPECIFICITY_PATTERNS = [
    re.compile(r"\d+"),                          # 数字（年・金額・割合など）
    re.compile(r"[都道府県市区町村]"),             # 地名
    re.compile(r"私は|私の|うち|職場|家族|子供|子ども"),  # 個人的言及
]


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _synthesis_direction(synthesis: dict) -> str:
    """synthesis の方向性を "positive" / "negative" / "neutral" で返す。"""
    text_parts = []
    for rec in synthesis.get("recommendations", []):
        text_parts.append(str(rec))
    text_parts.append(str(synthesis.get("overall_assessment", "")))
    combined = " ".join(text_parts)

    pos_count = sum(1 for kw in _POSITIVE_KEYWORDS if kw in combined)
    neg_count = sum(1 for kw in _NEGATIVE_KEYWORDS if kw in combined)

    if pos_count == 0 and neg_count == 0:
        return "neutral"
    if pos_count > neg_count:
        return "positive"
    if neg_count > pos_count:
        return "negative"
    return "neutral"


def _majority_direction(stance_distribution: dict) -> str:
    """stance_distribution から多数派の方向性を "positive" / "negative" / "neutral" で返す。

    "賛成" + "条件付き賛成" の合計 vs "反対" + "条件付き反対" の合計を比較し、
    どちらかが 50% 超なら該当方向を返す。それ以外は "neutral"。
    """
    pro = stance_distribution.get("賛成", 0.0) + stance_distribution.get("条件付き賛成", 0.0)
    con = stance_distribution.get("反対", 0.0) + stance_distribution.get("条件付き反対", 0.0)

    if pro > 0.50:
        return "positive"
    if con > 0.50:
        return "negative"
    return "neutral"


def _is_high_quality_response(response: dict) -> tuple[bool, list[str]]:
    """レスポンスが高品質かどうかを判定する。

    Returns:
        (is_high_quality, issues): 品質フラグと問題点リスト
    """
    issues: list[str] = []
    reason = response.get("reason", "")

    # デフォルトパターン検出: stance == "中立" and confidence == 0.5
    if response.get("stance") == "中立" and response.get("confidence") == 0.5:
        issues.append("デフォルトパターン (stance=中立, confidence=0.5)")

    # reason の長さチェック
    if len(reason) < _MIN_REASON_LENGTH:
        issues.append(f"reason が短すぎる ({len(reason)} 文字 < {_MIN_REASON_LENGTH} 文字)")

    # 具体性チェック（長さが十分な場合のみ）
    if len(reason) >= _MIN_REASON_LENGTH:
        has_specific = any(pat.search(reason) for pat in _SPECIFICITY_PATTERNS)
        if not has_specific:
            issues.append("具体的な詳細（数字・地名・個人的言及）が不足")

    return len(issues) == 0, issues


def classify_response_quality(response: dict) -> str:
    """レスポンスを3段階の品質 tier に分類する。

    Returns:
        "high" — 全チェックパス (長さ100+, 具体性あり, 非デフォルトパターン, confidence≠0.5)
        "medium" — 長さOKだが具体性不足、または confidence=0.5 ちょうど
        "low" — 長さ不足、デフォルトパターン、_failed フラグ
    """
    # _failed フラグ → 即 low
    if response.get("_failed"):
        return "low"

    reason = response.get("reason", "")
    stance = response.get("stance", "中立")
    confidence = response.get("confidence", 0.5)

    # デフォルトパターン (stance=中立 + confidence=0.5) → low
    if stance == "中立" and confidence == 0.5:
        return "low"

    # reason が短すぎる → low
    if len(reason) < _MIN_REASON_LENGTH:
        return "low"

    # ここから medium vs high の判定
    has_specific = any(pat.search(reason) for pat in _SPECIFICITY_PATTERNS)

    # 具体性なし → medium
    if not has_specific:
        return "medium"

    # confidence が 0.5 ちょうど → medium（LLM のデフォルト出力の疑い）
    if confidence == 0.5:
        return "medium"

    return "high"


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def validate_activation_meeting_consistency(aggregation: dict, synthesis: dict) -> dict:
    """活性化集計結果と会議 synthesis の方向性の整合性を検証する。

    Args:
        aggregation: stance_distribution を含む集計辞書
        synthesis: recommendations / overall_assessment を含む会議結果辞書

    Returns:
        {"status": "ok"|"warning", "type": str|None, "detail": str}
    """
    stance_distribution = aggregation.get("stance_distribution", {})
    if not stance_distribution:
        return {"status": "ok", "type": None, "detail": "stance_distribution が空のためチェックをスキップ"}

    majority_dir = _majority_direction(stance_distribution)
    if majority_dir == "neutral":
        # 多数派が中立 → 整合性チェック不要
        return {"status": "ok", "type": None, "detail": "多数派スタンスが中立のため整合性チェックをスキップ"}

    synth_dir = _synthesis_direction(synthesis)
    if synth_dir == "neutral":
        # synthesis の方向が不明 → チェック不能
        return {"status": "ok", "type": None, "detail": "synthesis の方向性が不明のためチェックをスキップ"}

    if majority_dir != synth_dir:
        pro = stance_distribution.get("賛成", 0.0) + stance_distribution.get("条件付き賛成", 0.0)
        con = stance_distribution.get("反対", 0.0) + stance_distribution.get("条件付き反対", 0.0)
        dominant_pct = max(pro, con) * 100
        return {
            "status": "warning",
            "type": "representation_gap",
            "detail": (
                f"多数派スタンスは {majority_dir} ({dominant_pct:.0f}%) だが、"
                f"synthesis は {synth_dir} を示している。少数派意見の過大代表の可能性がある。"
            ),
        }

    return {"status": "ok", "type": None, "detail": "整合性チェック問題なし"}


def validate_response_quality(responses: list[dict]) -> dict:
    """活性化レスポンスの品質を検証する。

    Args:
        responses: 各エージェントの応答辞書リスト

    Returns:
        {
            "response_quality_rate": float,  # 高品質割合 (0.0〜1.0)
            "low_quality_count": int,
            "total": int,
            "issues": list[str],             # 全問題点のリスト
        }
    """
    if not responses:
        return {
            "response_quality_rate": 1.0,
            "low_quality_count": 0,
            "total": 0,
            "issues": [],
        }

    high_quality_count = 0
    all_issues: list[str] = []

    for i, response in enumerate(responses):
        is_hq, issues = _is_high_quality_response(response)
        if is_hq:
            high_quality_count += 1
        else:
            for issue in issues:
                all_issues.append(f"[response {i}] {issue}")

    total = len(responses)
    return {
        "response_quality_rate": high_quality_count / total,
        "low_quality_count": total - high_quality_count,
        "total": total,
        "issues": all_issues,
    }


def explain_activation_meeting_gap(
    aggregation: dict,
    synthesis: dict,
    meeting_participants: list[dict] | None = None,
    propagation_data: dict | None = None,
) -> dict:
    """Explain why activation results and meeting conclusions diverge.

    Decomposes the gap into contributing factors such as:
    - Meeting composition bias (over/under-representation of stances)
    - Expert influence on final judgment
    - Network propagation shift
    - Opinion clustering effects

    Returns:
        {
            "gap_description": str,
            "gap_severity": "none"|"low"|"medium"|"high",
            "factors": [{"factor": str, "description": str}, ...],
            "activation_support_rate": float,
            "meeting_judgment_score": float,
        }
    """
    stance_dist = aggregation.get("stance_distribution", {})
    judgment_score = synthesis.get("judgment_score", 0.5)

    # Compute activation support rate (pro ratio)
    pro_rate = stance_dist.get("賛成", 0.0) + stance_dist.get("条件付き賛成", 0.0)
    con_rate = stance_dist.get("反対", 0.0) + stance_dist.get("条件付き反対", 0.0)

    gap = abs(pro_rate - judgment_score)
    factors: list[dict] = []

    # --- Factor 0: Basic gap magnitude ---
    if gap > 0.1:
        factors.append({
            "factor": "score_divergence",
            "description": (
                f"Activation賛成系比率({pro_rate*100:.0f}%)と"
                f"会議判断スコア({judgment_score*100:.0f}%)の間に"
                f"{gap*100:.0f}ポイントの乖離がある。"
            ),
        })

    # --- Factor 1: Meeting composition bias ---
    if meeting_participants:
        citizen_participants = [
            p for p in meeting_participants if p.get("role") == "citizen_representative"
        ]
        if citizen_participants:
            meeting_con = sum(
                1 for p in citizen_participants
                if p.get("stance", "") in ("反対", "条件付き反対")
            )
            meeting_con_rate = meeting_con / len(citizen_participants)
            if abs(meeting_con_rate - con_rate) > 0.1:
                factors.append({
                    "factor": "meeting_composition_bias",
                    "description": (
                        f"Activation全体では反対系が{con_rate*100:.0f}%だが、"
                        f"会議の市民代表では{meeting_con_rate*100:.0f}%が反対系。"
                        f"会議構成が全体の意見分布を正確に反映していない。"
                    ),
                })

        # Expert influence
        experts = [p for p in meeting_participants if p.get("role") == "expert"]
        if experts:
            factors.append({
                "factor": "expert_influence",
                "description": (
                    f"{len(experts)}人の専門家が会議に参加。"
                    f"専門家の発言が最終判断スコアに不釣り合いな影響を与えた可能性がある。"
                ),
            })

    # --- Factor 2: Network propagation shift ---
    if propagation_data:
        ts_history = propagation_data.get("timestep_history", [])
        if len(ts_history) >= 2:
            initial_dist = ts_history[0].get("opinion_distribution", {})
            final_dist = ts_history[-1].get("opinion_distribution", {})
            initial_pro = initial_dist.get("条件付き賛成", 0) + initial_dist.get("賛成", 0)
            final_pro = final_dist.get("条件付き賛成", 0) + final_dist.get("賛成", 0)
            shift = final_pro - initial_pro
            if abs(shift) > 0.05:
                direction = "賛成方向" if shift > 0 else "反対方向"
                factors.append({
                    "factor": "network_propagation_shift",
                    "description": (
                        f"ネットワーク伝播により意見分布が{direction}に{abs(shift)*100:.0f}%シフトした"
                        f"（伝播前: 賛成系{initial_pro*100:.0f}% → 伝播後: {final_pro*100:.0f}%）。"
                        f"全{propagation_data.get('total_timesteps', 0)}ステップで"
                        f"{'収束' if propagation_data.get('converged') else '未収束'}。"
                    ),
                })

        # Cluster impact
        clusters = propagation_data.get("clusters", [])
        if len(clusters) >= 2:
            sizes = sorted([c.get("size", 0) for c in clusters], reverse=True)
            factors.append({
                "factor": "opinion_clustering",
                "description": (
                    f"{len(clusters)}個の意見クラスタが形成された"
                    f"（最大クラスタ: {sizes[0]}人、第2クラスタ: {sizes[1]}人）。"
                    f"クラスタ間の分極化が判断スコアを中心寄りに引き下げた可能性がある。"
                ),
            })

        # Echo chamber
        echo = propagation_data.get("echo_chamber", {})
        homophily = echo.get("homophily_index", 0)
        if homophily > 0.6:
            factors.append({
                "factor": "echo_chamber_effect",
                "description": (
                    f"エコーチェンバー係数が{homophily:.2f}と高く、"
                    f"同意見者同士の交流が優勢。異なる立場との対話が不足している可能性がある。"
                ),
            })

    # --- Classify severity ---
    if gap < 0.1:
        severity = "none"
    elif gap < 0.2:
        severity = "low"
    elif gap < 0.35:
        severity = "medium"
    else:
        severity = "high"

    # --- Build description ---
    if severity == "none":
        description = "Activation結果と会議判断はおおむね一致している。"
    else:
        description = (
            f"Activationでは賛成系が{pro_rate*100:.0f}%を占めるが、"
            f"会議の判断スコアは{judgment_score*100:.0f}%。"
            f"差分{gap*100:.0f}%の要因を以下に分解する。"
        )

    return {
        "gap_description": description,
        "gap_severity": severity,
        "factors": factors,
        "activation_support_rate": round(pro_rate, 4),
        "meeting_judgment_score": judgment_score,
    }


def validate_minority_preservation(aggregation: dict, narrative: dict) -> dict:
    """少数派スタンスが narrative の controversy_areas に言及されているか検証する。

    Args:
        aggregation: stance_distribution を含む集計辞書
        narrative: controversy_areas を含むナラティブ辞書

    Returns:
        {"status": "ok"|"warning", "missing_minorities": list[str]}
    """
    stance_distribution = aggregation.get("stance_distribution", {})
    controversy_areas = narrative.get("controversy_areas", [])

    # 少数派スタンスを特定 (< _MINORITY_THRESHOLD)
    # "中立" は具体的な立場を持たないためスキップする
    minority_stances = [
        stance
        for stance, ratio in stance_distribution.items()
        if ratio < _MINORITY_THRESHOLD and stance != "中立"
    ]

    if not minority_stances:
        return {"status": "ok", "missing_minorities": []}

    # controversy_areas の全テキストを結合して検索対象にする
    area_texts: list[str] = []
    for area in controversy_areas:
        area_texts.append(str(area.get("point", "")))
        for s in area.get("supporting_stances", []):
            area_texts.append(str(s))
    combined_text = " ".join(area_texts)

    missing: list[str] = []
    for stance in minority_stances:
        if stance not in combined_text:
            missing.append(stance)

    if missing:
        return {"status": "warning", "missing_minorities": missing}

    return {"status": "ok", "missing_minorities": []}
