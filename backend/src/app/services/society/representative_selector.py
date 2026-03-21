"""代表者選出: 活性化結果からスタンス別クラスタリング→代表者+専門家選出"""

import logging
import uuid
from collections import defaultdict
from pathlib import Path

import yaml

from src.app.config import settings

logger = logging.getLogger(__name__)

EXPERT_PERSONAS = [
    "economist", "sociologist", "technologist",
    "ethicist", "environmentalist", "policy_analyst",
]


def _load_expert_template(persona_name: str) -> dict:
    """専門家テンプレートを読み込む。"""
    template_path = settings.templates_dir / "ja" / "experts" / f"{persona_name}.yaml"
    if template_path.exists():
        with open(template_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _cluster_by_stance(
    agents: list[dict],
    responses: list[dict],
) -> dict[str, list[tuple[dict, dict]]]:
    """スタンス別にエージェントをクラスタリングする。"""
    clusters: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for agent, resp in zip(agents, responses):
        stance = resp.get("stance", "中立")
        clusters[stance].append((agent, resp))
    return clusters


def select_representatives(
    agents: list[dict],
    responses: list[dict],
    max_citizen_reps: int = 6,
    max_experts: int = 4,
) -> list[dict]:
    """活性化結果から Meeting Layer の参加者を選出する。

    Returns:
        list of participant dicts, each containing:
        - agent_profile: dict (AgentProfile data or expert persona)
        - response: dict (activation response or None for experts)
        - role: "citizen_representative" | "expert"
        - expertise: str (expert persona name, empty for citizens)
    """
    participants = []

    # === 市民代表の選出 ===
    clusters = _cluster_by_stance(agents, responses)

    # 各スタンスから信頼度の高い順に代表を選出
    per_cluster = max(1, max_citizen_reps // max(len(clusters), 1))
    citizen_count = 0

    for stance, pairs in sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True):
        # 信頼度順にソート
        sorted_pairs = sorted(pairs, key=lambda x: x[1].get("confidence", 0.5), reverse=True)
        for agent, resp in sorted_pairs[:per_cluster]:
            if citizen_count >= max_citizen_reps:
                break
            participants.append({
                "agent_profile": agent,
                "response": resp,
                "role": "citizen_representative",
                "expertise": "",
                "stance": stance,
            })
            citizen_count += 1
        if citizen_count >= max_citizen_reps:
            break

    # === 専門家の追加 ===
    # テーマに関連性の高い専門家を選択（Phase 1 では全専門家から上位N人）
    selected_experts = EXPERT_PERSONAS[:max_experts]

    for persona_name in selected_experts:
        template = _load_expert_template(persona_name)
        if not template:
            continue

        expert_profile = {
            "id": str(uuid.uuid4()),
            "agent_index": -1,
            "demographics": {
                "age": 50,
                "gender": "other",
                "occupation": template.get("display_name", persona_name),
                "region": "専門家パネル",
                "education": "doctorate",
                "income_bracket": "high",
            },
            "big_five": {"O": 0.8, "C": 0.7, "E": 0.6, "A": 0.5, "N": 0.3},
            "values": {},
            "speech_style": "分析的で論理的",
            "llm_backend": "openai",  # 専門家は高品質プロバイダ
        }

        participants.append({
            "agent_profile": expert_profile,
            "response": None,
            "role": "expert",
            "expertise": persona_name,
            "display_name": template.get("display_name", persona_name),
            "persona": template.get("persona", {}),
            "prompts": template.get("prompts", {}),
        })

    logger.info(
        "Selected %d participants for meeting: %d citizens, %d experts",
        len(participants),
        sum(1 for p in participants if p["role"] == "citizen_representative"),
        sum(1 for p in participants if p["role"] == "expert"),
    )
    return participants
