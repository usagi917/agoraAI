"""活性化レイヤー: 選抜された住民をLLMで活性化し、意見分布を集計する"""

import logging
import re
from collections import Counter
from typing import Any

from src.app.llm.multi_client import multi_llm_client
from src.app.services.society.activation_prompts import build_activation_prompt
from src.app.services.society.output_validator import classify_response_quality
from src.app.services.society.statistical_inference import (
    bootstrap_confidence_intervals,
    compute_poststratification_weights,
    effective_sample_size,
    load_target_marginals,
    margin_of_error,
    weighted_stance_distribution,
)

logger = logging.getLogger(__name__)


def _temperature_from_big_five(big_five: dict, base_temperature: float = 0.5) -> float:
    """Big Five特性からLLM温度を算出する。

    開放性(O)が高い → 高温度（意外性のある発言）
    誠実性(C)が高い → 低温度（精密で地に足ついた発言）
    外向性(E)が高い → やや高温度（活発な表現）
    神経症傾向(N)が高い → やや高温度（感情的な揺れ）
    """
    o = big_five.get("O", 0.5)
    c = big_five.get("C", 0.5)
    e = big_five.get("E", 0.5)
    n = big_five.get("N", 0.5)

    # 基準からの偏差を計算（-0.25 ~ +0.25 の範囲）
    delta = (
        (o - 0.5) * 0.30   # 開放性: 最も影響大
        + (e - 0.5) * 0.15  # 外向性
        + (n - 0.5) * 0.10  # 神経症傾向
        - (c - 0.5) * 0.25  # 誠実性: 温度を下げる方向
    )

    temperature = base_temperature + delta
    return round(max(0.2, min(0.95, temperature)), 2)

# テキストからスタンスキーワードを抽出するための正規表現
_STANCE_PATTERNS: list[tuple[str, str]] = [
    (r"条件付き賛成", "条件付き賛成"),
    (r"条件付き反対", "条件付き反対"),
    (r"賛成", "賛成"),
    (r"反対", "反対"),
    (r"中立", "中立"),
]

_CONFIDENCE_PATTERN = re.compile(r"(?:confidence|信頼度|確信度)[:\s]*([01]\.?\d*)")
_QUALITY_WEIGHT: dict[str, float] = {"high": 1.0, "medium": 0.7, "low": 0.3}


def _extract_stance_from_text(text: str) -> dict | None:
    """文字列からスタンスキーワードをベストエフォートで抽出する。"""
    if not text or len(text) < 5:
        return None

    stance = None
    for pattern, label in _STANCE_PATTERNS:
        if re.search(pattern, text):
            stance = label
            break

    if stance is None:
        return None

    confidence = 0.5
    m = _CONFIDENCE_PATTERN.search(text)
    if m:
        try:
            confidence = max(0.0, min(1.0, float(m.group(1))))
        except ValueError:
            pass

    return {
        "stance": stance,
        "confidence": confidence,
        "reason": text[:150],
        "concern": "",
        "priority": "",
        "_recovered_from_text": True,
    }


def _parse_activation_response(result: dict | str) -> dict:
    """活性化レスポンスをパースする。"""
    # LLM呼び出しが完全に失敗した場合（エラー構造体）
    if isinstance(result, dict) and result.get("_error"):
        logger.error("Activation received error response: %s", result.get("_error_msg", ""))
        return {
            "stance": "",
            "confidence": 0.0,
            "reason": "",
            "concern": "",
            "priority": "",
            "_failed": True,
        }

    if isinstance(result, dict):
        return {
            "stance": result.get("stance", "中立"),
            "confidence": float(result.get("confidence", 0.5)),
            "reason": result.get("reason", ""),
            "concern": result.get("concern", ""),
            "priority": result.get("priority", ""),
        }

    # 文字列の場合: テキストからスタンスキーワード抽出を試みる
    text = str(result) if result else ""
    if not text.strip():
        logger.error("Activation received empty string response")
        return {
            "stance": "",
            "confidence": 0.0,
            "reason": "",
            "concern": "",
            "priority": "",
            "_failed": True,
        }

    recovered = _extract_stance_from_text(text)
    if recovered:
        logger.warning("Activation response recovered from text: stance=%s", recovered["stance"])
        return recovered

    # 回復不能 → 失敗としてマーク
    logger.warning("Activation response could not be parsed: %.100s...", text)
    return {
        "stance": "",
        "confidence": 0.0,
        "reason": text[:150],
        "concern": "",
        "priority": "",
        "_failed": True,
    }


def _aggregate_opinions(
    responses: list[dict],
    agents: list[dict] | None = None,
    independence_weights: dict[str, float] | None = None,
) -> dict:
    """意見分布を集計する。_failed レスポンスは除外。

    Args:
        responses: 各エージェントの活性化レスポンスリスト。
        agents: エージェントの辞書リスト。渡された場合は統計的推論（事後層化・
                ブートストラップCI・実効標本数）を実行する。None の場合は
                従来互換の処理のみ行う。
        independence_weights: エージェントID→独立性重みの辞書。渡された場合は
                人口統計重みと乗算して最終重みとする。None の場合は従来互換。

    Returns:
        集計結果の辞書。agents が渡された場合は以下のキーが追加される:
        - stance_distribution_raw: ウェイト付けなしの元の分布
        - confidence_intervals: 各スタンスのブートストラップ95%CI
        - margin_of_error: 全スタンス中の最大誤差幅
        - effective_sample_size: 実効標本サイズ (Kish 1965)
        - design_effect: n / n_eff
        - weighting_applied: True（ウェイト付けが実行された場合）
        - independence_weighting_applied: True（独立性重みが適用された場合）
        - low_sample_warning: n_eff < 30 の場合 True
    """
    total_submitted = len(responses)
    valid_responses = [r for r in responses if not r.get("_failed")]
    failed_count = total_submitted - len(valid_responses)

    if failed_count > 0:
        logger.warning(
            "Activation aggregation: %d/%d responses failed and excluded",
            failed_count, total_submitted,
        )

    if not valid_responses:
        return {
            "total_respondents": 0,
            "total_submitted": total_submitted,
            "failed_count": failed_count,
            "stance_distribution": {},
            "average_confidence": 0.0,
            "top_concerns": [],
            "top_priorities": [],
        }

    stance_counter = Counter(r["stance"] for r in valid_responses)
    total = len(valid_responses)

    # 信頼度の平均
    avg_confidence = sum(r["confidence"] for r in valid_responses) / total

    # スタンス分布（正規化）
    distribution = {
        stance: round(count / total, 4)
        for stance, count in stance_counter.most_common()
    }

    # 主要な懸念事項
    concern_counter = Counter(r["concern"] for r in valid_responses if r["concern"])
    top_concerns = [item for item, _ in concern_counter.most_common(5)]

    # 主要な優先事項
    priority_counter = Counter(r["priority"] for r in valid_responses if r["priority"])
    top_priorities = [item for item, _ in priority_counter.most_common(5)]

    result = {
        "total_respondents": total,
        "total_submitted": total_submitted,
        "failed_count": failed_count,
        "stance_distribution": distribution,
        "average_confidence": round(avg_confidence, 4),
        "top_concerns": top_concerns,
        "top_priorities": top_priorities,
    }

    # agents が渡された場合: 統計的推論を実行
    if agents is not None:
        # _failed でないレスポンスに対応するエージェントを揃える
        # responses と agents は同じ長さ・同じ順序を想定
        valid_pairs = [
            (ag, r)
            for ag, r in zip(agents, responses)
            if not r.get("_failed")
        ]
        valid_agents_subset = [ag for ag, _ in valid_pairs]

        # 事後層化ウェイトを算出
        target_marginals = load_target_marginals()
        try:
            weights = compute_poststratification_weights(
                valid_agents_subset, valid_responses, target_marginals
            )
            weighting_applied = True
        except Exception as exc:
            logger.warning("Poststratification weight computation failed: %s", exc)
            weights = [1.0] * len(valid_responses)
            weighting_applied = False

        # 品質重みを乗算（medium は 0.7 倍、low は 0.3 倍）
        for i, resp in enumerate(valid_responses):
            tier = classify_response_quality(resp)
            weights[i] = weights[i] * _QUALITY_WEIGHT.get(tier, 1.0)

        # 独立性重みを乗算（クラスター相関の割引）
        independence_weighting_applied = False
        if independence_weights is not None:
            for i, ag in enumerate(valid_agents_subset):
                agent_id = ag.get("id", "")
                ind_w = independence_weights.get(agent_id, 1.0)
                weights[i] = weights[i] * ind_w
            independence_weighting_applied = True

        # 実効標本サイズ
        try:
            n_eff = effective_sample_size(weights)
        except Exception as exc:
            logger.warning("Effective sample size computation failed: %s", exc)
            n_eff = float(total)

        # ウェイト付きスタンス分布
        weighted_dist = weighted_stance_distribution(valid_responses, weights)

        # ブートストラップ信頼区間
        try:
            ci_dict = bootstrap_confidence_intervals(
                valid_responses, weights, n_bootstrap=500, seed=42
            )
        except Exception as exc:
            logger.warning("Bootstrap CI computation failed: %s", exc)
            ci_dict = {}

        # 各スタンスの誤差幅（最大値）
        max_moe = 0.0
        for stance, proportion in weighted_dist.items():
            try:
                moe = margin_of_error(proportion, n_eff)
                max_moe = max(max_moe, moe)
            except Exception:
                pass

        # design_effect = n / n_eff
        design_effect = total / n_eff if n_eff > 0 else 1.0

        result.update({
            "stance_distribution_raw": distribution,
            "stance_distribution": weighted_dist,
            "confidence_intervals": ci_dict,
            "margin_of_error": round(max_moe, 4),
            "effective_sample_size": round(n_eff, 2),
            "design_effect": round(design_effect, 4),
            "weighting_applied": weighting_applied,
            "independence_weighting_applied": independence_weighting_applied,
            "low_sample_warning": n_eff < 30,
        })

    return result


def _select_representatives(
    agents: list[dict],
    responses: list[dict],
    count: int = 8,
) -> list[dict]:
    """スタンス別に代表者を選出する。_failed レスポンスは除外。"""
    # 有効なレスポンスのみでグループ化
    stance_groups: dict[str, list[tuple[dict, dict]]] = {}
    for agent, resp in zip(agents, responses):
        if resp.get("_failed"):
            continue
        stance = resp["stance"]
        if stance not in stance_groups:
            stance_groups[stance] = []
        stance_groups[stance].append((agent, resp))

    if not stance_groups:
        logger.error("No valid responses available for representative selection")
        return []

    representatives = []
    # 各スタンスから信頼度の高い順に選出
    per_stance = max(1, count // len(stance_groups))
    for stance, pairs in stance_groups.items():
        sorted_pairs = sorted(pairs, key=lambda x: x[1]["confidence"], reverse=True)
        for agent, resp in sorted_pairs[:per_stance]:
            representatives.append({
                "agent": agent,
                "response": resp,
            })

    return representatives[:count]


async def run_activation(
    agents: list[dict],
    theme: str,
    temperature: float = 0.5,
    max_tokens: int = 1024,
    max_concurrency: int = 30,
    on_progress: Any = None,
) -> dict:
    """活性化レイヤーを実行する。

    Returns:
        {
            "responses": list[dict],        # 各住民の回答
            "aggregation": dict,             # 集計結果
            "representatives": list[dict],   # 代表者リスト
            "usage": dict,                   # トークン使用量合計
        }
    """
    multi_llm_client.initialize()

    # プロンプト構築
    calls = []
    for agent in agents:
        system_prompt, user_prompt = build_activation_prompt(
            agent, theme, grounding_facts=agent.get("grounding_facts")
        )
        agent_temperature = _temperature_from_big_five(
            agent.get("big_five", {}), base_temperature=temperature,
        )
        calls.append({
            "provider": agent.get("llm_backend", "openai"),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": agent_temperature,
            "max_tokens": max_tokens,
        })

    # バッチ呼び出し
    raw_results = await multi_llm_client.call_batch_by_provider(calls, max_concurrency)

    # レスポンスパース
    responses = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    provider_usage: dict[str, dict] = {}

    for i, (result, usage) in enumerate(raw_results):
        parsed = _parse_activation_response(result)
        responses.append(parsed)

        total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        total_usage["total_tokens"] += usage.get("total_tokens", 0)

        provider = usage.get("provider", "unknown")
        if provider not in provider_usage:
            provider_usage[provider] = {"calls": 0, "total_tokens": 0}
        provider_usage[provider]["calls"] += 1
        provider_usage[provider]["total_tokens"] += usage.get("total_tokens", 0)

        if on_progress and (i + 1) % 10 == 0:
            await on_progress(i + 1, len(agents))

    # 集計（agents を渡して統計的推論を有効化）
    aggregation = _aggregate_opinions(responses, agents=agents)

    # 代表者選出
    representatives = _select_representatives(agents, responses)

    logger.info(
        "Activation completed: %d responses, distribution=%s",
        len(responses), aggregation["stance_distribution"],
    )

    return {
        "responses": responses,
        "aggregation": aggregation,
        "representatives": representatives,
        "usage": {**total_usage, "by_provider": provider_usage},
    }
