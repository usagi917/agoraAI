"""テスト用ファクトリ関数"""

import uuid
from datetime import datetime, timezone
from src.app.models.simulation import Simulation


def make_simulation(**overrides) -> Simulation:
    """Simulation インスタンスを生成する。"""
    defaults = {
        "id": str(uuid.uuid4()),
        "mode": "unified",
        "prompt_text": "テスト用プロンプト",
        "template_name": "general_analysis",
        "execution_profile": "preview",
        "status": "queued",
        "metadata_json": {},
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Simulation(**defaults)


def make_responses(stances: list[str], confidence: float = 0.7) -> list[dict]:
    """テスト用の response リストを生成する。"""
    return [
        {"stance": s, "confidence": confidence, "reason": f"理由: {s}"}
        for s in stances
    ]


def make_agents(count: int, openness: float = 0.5) -> list[dict]:
    """テスト用の agent リストを生成する。"""
    return [
        {
            "big_five": {"O": openness, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
            "values": {},
        }
        for _ in range(count)
    ]


def make_pulse_result(**overrides) -> dict:
    """SocietyPulseResult 相当のデータを生成する。"""
    defaults = {
        "agents": make_agents(5),
        "responses": make_responses(["賛成", "反対", "中立", "賛成", "反対"]),
        "aggregation": {
            "stance_distribution": {"賛成": 0.4, "反対": 0.4, "中立": 0.2},
            "average_confidence": 0.65,
            "top_concerns": ["コスト", "実現可能性"],
            "top_priorities": ["効率化"],
            "total_respondents": 5,
        },
        "evaluation": {
            "diversity": 0.95,
            "consistency": 0.7,
            "calibration": 0.8,
        },
        "representatives": [],
        "usage": {"total_tokens": 100},
        "population_count": 100,
    }
    defaults.update(overrides)
    return defaults


def make_council_result(**overrides) -> dict:
    """CouncilResult 相当のデータを生成する。"""
    defaults = {
        "participants": [{"name": "Agent-1", "role": "expert"}],
        "devil_advocate_summary": "反論要約テスト",
        "kg_entities": [],
        "kg_relations": [],
        "rounds": [{"round": 1, "arguments": []}],
        "synthesis": {
            "consensus_points": ["全員が安全性を重視"],
            "disagreement_points": [{"topic": "コスト", "positions": []}],
            "recommendations": ["段階的導入を推奨"],
            "overall_assessment": "条件付き推進が妥当",
            "scenarios": [],
        },
        "usage": {"total_tokens": 200},
    }
    defaults.update(overrides)
    return defaults


def make_llm_response(
    content: dict | str | None = None, tokens: int = 100
) -> tuple:
    """LLM 呼び出しの戻り値をモック用に生成する。"""
    if content is None:
        content = {"result": "ok"}
    usage = {
        "prompt_tokens": tokens // 2,
        "completion_tokens": tokens // 2,
        "total_tokens": tokens,
    }
    return content, usage
