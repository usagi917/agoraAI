"""Benchmark the local Liquid activation path without making paid API calls."""

from __future__ import annotations

import argparse
import asyncio
import json
import time

from src.app.services.society.activation_layer import run_activation


def _agents(count: int) -> list[dict]:
    return [
        {
            "id": f"benchmark-agent-{index}",
            "agent_index": index,
            "demographics": {
                "age": 20 + index % 65,
                "gender": "female" if index % 2 else "male",
                "region": ["関東", "関西", "東北", "九州"][index % 4],
                "occupation": ["会社員", "自営業", "介護士", "学生"][index % 4],
                "income_bracket": ["low", "middle", "high"][index % 3],
                "education": ["high_school", "bachelor", "graduate"][index % 3],
                "employment_status": ["employed", "self_employed", "student"][index % 3],
                "household_type": ["single", "couple", "couple_with_children"][index % 3],
            },
            "big_five": {
                "O": 0.3 + (index % 6) * 0.1,
                "C": 0.7 - (index % 5) * 0.1,
                "E": 0.2 + (index % 7) * 0.1,
                "A": 0.4 + (index % 4) * 0.1,
                "N": 0.6 - (index % 5) * 0.1,
            },
            "values": {"security": 0.8, "fairness": 0.7, "growth": 0.5},
            "speech_style": "率直で簡潔",
        }
        for index in range(count)
    ]


async def _run(count: int, concurrency: int) -> None:
    agents = _agents(count)
    started = time.perf_counter()
    result = await run_activation(
        agents,
        "公共交通料金を10%値上げし、設備更新と運転手の賃上げに充てる政策",
        provider_override="liquid",
        compact=True,
        minimal=True,
        max_tokens=160,
        max_concurrency=concurrency,
        chunk_size=128,
        abort_on_full_chunk_failure=True,
        require_provider_ready=True,
    )
    elapsed = time.perf_counter() - started
    valid = sum(not response.get("_failed") for response in result["responses"])
    total_tokens = int(result["usage"].get("total_tokens", 0) or 0)
    summary = {
        "agents": count,
        "valid": valid,
        "valid_rate": valid / count if count else 0,
        "elapsed_seconds": round(elapsed, 3),
        "agents_per_second": round(count / elapsed, 3) if elapsed else 0,
        "tokens_per_second": round(total_tokens / elapsed, 3) if elapsed else 0,
        "projected_10k_minutes": round((elapsed / count * 10_000) / 60, 1) if count else 0,
        "usage": result["usage"],
        "distribution": result["aggregation"].get("stance_distribution", {}),
        "sample": result["responses"][0] if result["responses"] else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()
    asyncio.run(_run(max(1, args.count), max(1, args.concurrency)))


if __name__ == "__main__":
    main()
