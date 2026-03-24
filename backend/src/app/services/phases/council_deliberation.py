"""Council Deliberation フェーズ: 名前生成 + 反証役 + 3ラウンド議論 + KG進化"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from src.app.config import settings
from src.app.llm.multi_client import multi_llm_client
from src.app.models.simulation import Simulation
from src.app.services.phases.society_pulse import SocietyPulseResult
from src.app.services.society.kg_updater import extract_kg_updates_from_round, apply_kg_updates
from src.app.services.society.meeting_layer import run_meeting
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


@dataclass
class CouncilResult:
    participants: list[dict]
    rounds: list[list[dict]]
    synthesis: dict
    devil_advocate_summary: str
    usage: dict
    kg_entities: list[dict] = field(default_factory=list)
    kg_relations: list[dict] = field(default_factory=list)


def _assign_devil_advocates(
    participants: list[dict],
    max_advocates: int = 3,
) -> list[dict]:
    """参加者の中から反証役を指定する。

    少数派スタンスの citizen 1人 + expert 2人を反証役に選ぶ。
    """
    # スタンス分布を計算
    stance_counts: Counter[str] = Counter()
    for p in participants:
        if p["role"] == "citizen_representative":
            stance_counts[p.get("stance", "中立")] += 1

    # 少数派スタンスを特定
    minority_stance = stance_counts.most_common()[-1][0] if stance_counts else "中立"

    advocates_assigned = 0

    # 少数派 citizen から1人
    for p in participants:
        if (
            p["role"] == "citizen_representative"
            and p.get("stance") == minority_stance
            and advocates_assigned < max_advocates
        ):
            p["is_devil_advocate"] = True
            advocates_assigned += 1
            break

    # expert から残りを補充
    for p in participants:
        if advocates_assigned >= max_advocates:
            break
        if p["role"] == "expert" and not p.get("is_devil_advocate"):
            p["is_devil_advocate"] = True
            advocates_assigned += 1

    # まだ足りなければ citizen から追加
    for p in participants:
        if advocates_assigned >= max_advocates:
            break
        if not p.get("is_devil_advocate"):
            p["is_devil_advocate"] = True
            advocates_assigned += 1

    return participants


async def _generate_names(
    participants: list[dict],
) -> list[str]:
    """参加者の demographics に基づいて日本語名をバッチ生成する。

    LLM に1回呼び出しで全参加者分の名前を生成する。
    """
    multi_llm_client.initialize()

    descriptions = []
    for i, p in enumerate(participants):
        if p["role"] == "citizen_representative":
            demo = p.get("agent_profile", {}).get("demographics", {})
            descriptions.append(
                f"{i+1}. {demo.get('region', '不明')}在住・{demo.get('age', 30)}歳・{demo.get('gender', '不明')}"
            )
        else:
            descriptions.append(f"{i+1}. 専門家（{p.get('expertise', '不明')}）")

    system_prompt = (
        "あなたは日本語の名前生成器です。以下の人物リストに対して、それぞれ自然な日本語のフルネームを生成してください。\n"
        "名前のみをリストで返してください。1行に1名。番号は不要です。\n"
        "地域・年齢・性別に合った自然な名前にしてください。"
    )
    user_prompt = "\n".join(descriptions)

    try:
        result, _usage = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.8,
            max_tokens=1024,
        )

        if isinstance(result, str):
            names = [line.strip() for line in result.strip().split("\n") if line.strip()]
        elif isinstance(result, dict):
            raw = result.get("names", result.get("content", ""))
            if isinstance(raw, list):
                names = raw
            else:
                names = [line.strip() for line in str(raw).strip().split("\n") if line.strip()]
        else:
            names = []

        # 足りない場合はフォールバック名を追加
        while len(names) < len(participants):
            names.append(f"参加者{len(names)+1}")

        return names[:len(participants)]

    except Exception as e:
        logger.warning("Name generation failed, using fallback names: %s", e)
        return [f"参加者{i+1}" for i in range(len(participants))]


async def run_council(
    session: Any,
    sim: Simulation,
    pulse: SocietyPulseResult,
    theme: str,
    kg_entities: list[dict] | None = None,
    kg_relations: list[dict] | None = None,
) -> CouncilResult:
    """Council Deliberation フェーズを実行する。

    10人の代表者に名前を付与し、反証役を指定して3ラウンドの議論を行う。
    議論の各ラウンドからKGを進化させる。
    """
    simulation_id = sim.id
    participants = list(pulse.representatives)

    # 名前生成
    names = await _generate_names(participants)

    # 名前を参加者に注入
    for i, p in enumerate(participants):
        name = names[i]
        if p["role"] == "citizen_representative":
            demo = p.get("agent_profile", {}).get("demographics", {})
            p["display_name"] = f"{name}（{demo.get('occupation', '')}・{demo.get('age', '')}歳・{demo.get('region', '')}）"
        else:
            p["display_name"] = f"{name}（{p.get('expertise', '専門家')}）"

    # 反証役の指定
    participants = _assign_devil_advocates(participants, max_advocates=3)

    await sse_manager.publish(simulation_id, "meeting_started", {
        "participant_count": len(participants),
        "num_rounds": 3,
        "participants": [
            {
                "display_name": p.get("display_name", ""),
                "role": p["role"],
                "is_devil_advocate": p.get("is_devil_advocate", False),
            }
            for p in participants
        ],
    })

    # Meeting 実行
    meeting_result = await run_meeting(
        participants,
        theme,
        simulation_id=simulation_id,
        num_rounds=3,
        session=session,
    )

    # 反証サマリーを抽出（participant_index ベースでマッチング）
    devil_advocate_indices = {
        i for i, p in enumerate(participants) if p.get("is_devil_advocate")
    }
    devil_arguments = []
    for round_args in meeting_result.get("rounds", []):
        for arg in round_args:
            if arg.get("participant_index") in devil_advocate_indices:
                text = (arg.get("argument") or "").strip()
                if text:
                    devil_arguments.append(text)

    if devil_arguments:
        devil_advocate_summary = "反証役の主な主張: " + " / ".join(devil_arguments[:3])
    else:
        # 引数が空の場合: devil advocate の初期スタンス・懸念からフォールバック生成
        fallback_parts = []
        for p in participants:
            if p.get("is_devil_advocate"):
                stance = p.get("stance", "")
                concern = p.get("response", {}).get("concern", "") if p.get("response") else ""
                reason = p.get("response", {}).get("reason", "") if p.get("response") else ""
                part = concern or reason or stance
                if part:
                    fallback_parts.append(part)
        if fallback_parts:
            devil_advocate_summary = "反証役の懸念: " + " / ".join(fallback_parts[:3])
        else:
            devil_advocate_summary = "反証なし"

    # === KG 進化: ラウンドごとに新エンティティ・関係を抽出 ===
    evolved_entities = list(kg_entities) if kg_entities else []
    evolved_relations = list(kg_relations) if kg_relations else []

    if evolved_entities:
        existing_names = {e.get("name", "") for e in evolved_entities}
        for round_idx, round_args in enumerate(meeting_result.get("rounds", [])):
            try:
                updates = await extract_kg_updates_from_round(
                    round_args, theme, existing_names,
                )
                if updates.get("new_entities") or updates.get("updated_entities"):
                    evolved_entities, evolved_relations = apply_kg_updates(
                        evolved_entities, evolved_relations, updates,
                    )
                    existing_names = {e.get("name", "") for e in evolved_entities}
                    logger.info(
                        "KG evolved after round %d: +%d entities, +%d relations",
                        round_idx + 1,
                        len(updates.get("new_entities", [])),
                        len(updates.get("new_relations", [])),
                    )
            except Exception as e:
                logger.warning("KG evolution failed for round %d: %s", round_idx + 1, e)

    await sse_manager.publish(simulation_id, "meeting_completed", {
        "rounds": len(meeting_result.get("rounds", [])),
        "synthesis_available": bool(meeting_result.get("synthesis")),
        "devil_advocate_summary": devil_advocate_summary[:200],
        "kg_evolved": len(evolved_entities) > len(kg_entities or []),
    })

    # 参加者サマリーを構築
    participant_summaries = []
    for p in participants:
        summary = {
            "display_name": p.get("display_name", ""),
            "role": p["role"],
            "is_devil_advocate": p.get("is_devil_advocate", False),
            "expertise": p.get("expertise", ""),
        }
        if p["role"] == "citizen_representative":
            summary["stance"] = p.get("stance", "")
        participant_summaries.append(summary)

    return CouncilResult(
        participants=participant_summaries,
        rounds=meeting_result.get("rounds", []),
        synthesis=meeting_result.get("synthesis", {}),
        devil_advocate_summary=devil_advocate_summary,
        usage=meeting_result.get("usage", {}),
        kg_entities=evolved_entities,
        kg_relations=evolved_relations,
    )
