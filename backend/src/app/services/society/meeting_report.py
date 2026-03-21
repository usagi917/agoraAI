"""Meeting レポート生成: 議論からシナリオ・合意点・対立点・スタンス変化を構造化抽出"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _extract_stance_shifts(rounds: list[list[dict]]) -> list[dict]:
    """ラウンド間のスタンス変化を検出する。"""
    if len(rounds) < 2:
        return []

    # 参加者の初期・最終ポジションを比較
    first_round = {arg["participant_name"]: arg.get("position", "") for arg in rounds[0]}
    last_round = {arg["participant_name"]: arg.get("position", "") for arg in rounds[-1]}

    shifts = []
    for name, initial_pos in first_round.items():
        final_pos = last_round.get(name, "")
        if initial_pos and final_pos and initial_pos != final_pos:
            shifts.append({
                "participant": name,
                "initial_position": initial_pos,
                "final_position": final_pos,
            })

    return shifts


def _extract_key_arguments(rounds: list[list[dict]]) -> list[dict]:
    """各ラウンドから主要な論点を抽出する。"""
    key_args = []
    for round_args in rounds:
        for arg in round_args:
            if arg.get("argument"):
                key_args.append({
                    "participant": arg.get("participant_name", ""),
                    "role": arg.get("role", ""),
                    "round": arg.get("round", 0),
                    "argument": arg["argument"],
                    "evidence": arg.get("evidence", ""),
                })
    return key_args


def _collect_all_concerns(rounds: list[list[dict]]) -> list[str]:
    """全ラウンドの懸念事項を収集・重複排除する。"""
    concerns = []
    seen = set()
    for round_args in rounds:
        for arg in round_args:
            for concern in arg.get("concerns", []):
                if concern and concern not in seen:
                    concerns.append(concern)
                    seen.add(concern)
    return concerns


def generate_meeting_report(meeting_result: dict) -> dict[str, Any]:
    """Meeting の結果から構造化レポートを生成する。

    Returns:
        {
            "summary": str,
            "participants": list,
            "rounds_summary": list,
            "key_arguments": list,
            "consensus_points": list,
            "disagreement_points": list,
            "stance_shifts": list,
            "scenarios": list,
            "concerns": list,
            "recommendations": list,
            "overall_assessment": str,
        }
    """
    rounds = meeting_result.get("rounds", [])
    synthesis = meeting_result.get("synthesis", {})
    participants = meeting_result.get("participants", [])

    # ラウンドサマリー
    rounds_summary = []
    for i, round_args in enumerate(rounds):
        round_names = ["初期主張", "相互質疑・反論", "最終立場表明"]
        name = round_names[i] if i < len(round_names) else f"ラウンド{i+1}"
        positions = [
            f"{arg.get('participant_name', '?')}: {arg.get('position', '')}"
            for arg in round_args
        ]
        rounds_summary.append({
            "round": i + 1,
            "name": name,
            "argument_count": len(round_args),
            "positions": positions,
        })

    # スタンス変化の検出
    stance_shifts = synthesis.get("stance_shifts", []) or _extract_stance_shifts(rounds)

    # 主要論点
    key_arguments = _extract_key_arguments(rounds)

    # 懸念事項
    all_concerns = _collect_all_concerns(rounds)

    # シナリオ（synthesis から）
    scenarios = synthesis.get("scenarios", [])

    # 全体サマリー
    citizen_count = sum(1 for p in participants if p.get("role") == "citizen_representative")
    expert_count = sum(1 for p in participants if p.get("role") == "expert")
    summary = (
        f"市民代表{citizen_count}名と専門家{expert_count}名による"
        f"{len(rounds)}ラウンドの構造化議論を実施。"
    )
    if synthesis.get("overall_assessment"):
        summary += f" {synthesis['overall_assessment']}"

    report = {
        "summary": summary,
        "participants": participants,
        "rounds_summary": rounds_summary,
        "key_arguments": key_arguments[:20],  # 上位20件
        "consensus_points": synthesis.get("consensus_points", []),
        "disagreement_points": synthesis.get("disagreement_points", []),
        "stance_shifts": stance_shifts,
        "scenarios": scenarios,
        "concerns": all_concerns[:10],
        "recommendations": synthesis.get("recommendations", []),
        "key_insights": synthesis.get("key_insights", []),
        "overall_assessment": synthesis.get("overall_assessment", ""),
    }

    logger.info(
        "Meeting report generated: %d arguments, %d consensus, %d disagreements, %d scenarios",
        len(key_arguments),
        len(report["consensus_points"]),
        len(report["disagreement_points"]),
        len(scenarios),
    )
    return report
