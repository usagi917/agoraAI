"""活性化レイヤー: 選抜された住民をLLMで活性化し、意見分布を集計する"""

import logging
from collections import Counter
from typing import Any

from src.app.llm.multi_client import multi_llm_client
from src.app.services.society.activation_prompts import build_activation_prompt

logger = logging.getLogger(__name__)


def _parse_activation_response(result: dict | str) -> dict:
    """活性化レスポンスをパースする。"""
    if isinstance(result, dict):
        return {
            "stance": result.get("stance", "中立"),
            "confidence": float(result.get("confidence", 0.5)),
            "reason": result.get("reason", ""),
            "concern": result.get("concern", ""),
            "priority": result.get("priority", ""),
        }
    # 文字列の場合はデフォルト値
    return {
        "stance": "中立",
        "confidence": 0.5,
        "reason": str(result)[:150] if result else "",
        "concern": "",
        "priority": "",
    }


def _aggregate_opinions(responses: list[dict]) -> dict:
    """意見分布を集計する。"""
    if not responses:
        return {
            "total_respondents": 0,
            "stance_distribution": {},
            "average_confidence": 0.0,
            "top_concerns": [],
            "top_priorities": [],
        }

    stance_counter = Counter(r["stance"] for r in responses)
    total = len(responses)

    # 信頼度の平均
    avg_confidence = sum(r["confidence"] for r in responses) / total if responses else 0.0

    # スタンス分布（正規化）
    distribution = {
        stance: round(count / total, 4)
        for stance, count in stance_counter.most_common()
    }

    # 主要な懸念事項
    concern_counter = Counter(r["concern"] for r in responses if r["concern"])
    top_concerns = [item for item, _ in concern_counter.most_common(5)]

    # 主要な優先事項
    priority_counter = Counter(r["priority"] for r in responses if r["priority"])
    top_priorities = [item for item, _ in priority_counter.most_common(5)]

    return {
        "total_respondents": total,
        "stance_distribution": distribution,
        "average_confidence": round(avg_confidence, 4),
        "top_concerns": top_concerns,
        "top_priorities": top_priorities,
    }


def _select_representatives(
    agents: list[dict],
    responses: list[dict],
    count: int = 8,
) -> list[dict]:
    """スタンス別に代表者を選出する。"""
    # スタンス別にグループ化
    stance_groups: dict[str, list[tuple[dict, dict]]] = {}
    for agent, resp in zip(agents, responses):
        stance = resp["stance"]
        if stance not in stance_groups:
            stance_groups[stance] = []
        stance_groups[stance].append((agent, resp))

    representatives = []
    # 各スタンスから信頼度の高い順に選出
    per_stance = max(1, count // len(stance_groups)) if stance_groups else 1
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
        system_prompt, user_prompt = build_activation_prompt(agent, theme)
        calls.append({
            "provider": agent.get("llm_backend", "openai"),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": temperature,
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

    # 集計
    aggregation = _aggregate_opinions(responses)

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
