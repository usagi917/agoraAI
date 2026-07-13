"""Run one structured activation against a configured hybrid provider."""

from __future__ import annotations

import argparse
import asyncio
import json

from src.app.llm.multi_client import multi_llm_client
from src.app.services.society.activation_layer import run_activation


async def _run(provider: str) -> None:
    agent = {
        "id": f"smoke-{provider}",
        "agent_index": 0,
        "demographics": {
            "age": 42,
            "gender": "female",
            "region": "関東",
            "occupation": "会社員",
            "income_bracket": "middle",
            "education": "bachelor",
        },
        "big_five": {"O": 0.6, "C": 0.7, "E": 0.4, "A": 0.6, "N": 0.3},
        "values": {"security": 0.8, "fairness": 0.7, "growth": 0.4},
    }
    try:
        result = await run_activation(
            [agent],
            "公共交通料金を10%値上げし、設備更新と賃上げに充てる政策",
            provider_override=provider,
            compact=True,
            max_tokens=250 if provider == "openai_escalation" else 120,
            max_concurrency=1,
            chunk_size=1,
        )
        print(
            json.dumps(
                {
                    "provider": provider,
                    "response": result["responses"][0],
                    "usage": result["usage"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await multi_llm_client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "provider",
        choices=("openai_shadow", "openai_escalation"),
    )
    args = parser.parse_args()
    asyncio.run(_run(args.provider))


if __name__ == "__main__":
    main()
