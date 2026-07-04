"""診断用の単一LLM 5分類分布ベースライン。"""

from __future__ import annotations

import json
import logging

from src.app.llm.multi_client import multi_llm_client
from src.app.services.society.constants import STANCE_ORDER
from src.app.services.society.survey_anchor import normalize_stance_distribution

logger = logging.getLogger(__name__)


UNIFORM_DISTRIBUTION = {stance: 1.0 / len(STANCE_ORDER) for stance in STANCE_ORDER}


def normalize_llm_distribution_payload(payload: object) -> dict[str, float]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("single-llm distribution returned invalid JSON; using uniform fallback")
            return dict(UNIFORM_DISTRIBUTION)

    if not isinstance(payload, dict):
        logger.warning("single-llm distribution returned non-dict payload; using uniform fallback")
        return dict(UNIFORM_DISTRIBUTION)

    distribution = payload.get("stance_distribution", payload)
    if not isinstance(distribution, dict):
        logger.warning("single-llm distribution missing stance distribution; using uniform fallback")
        return dict(UNIFORM_DISTRIBUTION)

    try:
        values = {stance: float(distribution.get(stance, 0.0)) for stance in STANCE_ORDER}
    except (TypeError, ValueError):
        logger.warning("single-llm distribution contained non-numeric values; using uniform fallback")
        return dict(UNIFORM_DISTRIBUTION)

    if sum(values.values()) <= 0:
        logger.warning("single-llm distribution had zero mass; using uniform fallback")
        return dict(UNIFORM_DISTRIBUTION)
    return normalize_stance_distribution(values)


async def run_single_llm_distribution(
    theme: str,
    seed: int,
    *,
    provider: str = "openai",
) -> dict[str, float]:
    """日本の有権者母集団の5分類スタンス分布を単一LLMで推定する。"""
    multi_llm_client.initialize()
    stance_keys = " / ".join(STANCE_ORDER)
    system_prompt = (
        "あなたは日本の世論調査方法論に詳しいリサーチャーです。"
        "政策テーマに対する日本の有権者母集団のスタンス分布を、"
        "5分類のJSONのみで推定してください。"
        f"キーは必ず {stance_keys} の5つを使い、値は合計1.0の数値にしてください。"
    )
    user_prompt = (
        f"テーマ: {theme}\n\n"
        "出力形式:\n"
        "{\n"
        '  "賛成": 0.0,\n'
        '  "条件付き賛成": 0.0,\n'
        '  "中立": 0.0,\n'
        '  "条件付き反対": 0.0,\n'
        '  "反対": 0.0\n'
        "}"
    )
    result, _usage = await multi_llm_client.call(
        provider_name=provider,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=512,
        seed=seed,
        response_format={"type": "json_object"},
    )
    return normalize_llm_distribution_payload(result)
