"""代表者選出: 活性化結果からスタンス別クラスタリング→代表者+専門家選出"""

import logging
import uuid
from collections import defaultdict
from pathlib import Path

import yaml

from src.app.config import settings
from src.app.llm.multi_client import multi_llm_client

logger = logging.getLogger(__name__)

EXPERT_PERSONAS = [
    "economist", "sociologist", "technologist",
    "ethicist", "environmentalist", "policy_analyst",
]

# テーマに応じて選べる追加の専門家タイプ
EXTENDED_EXPERT_POOL = [
    "economist", "sociologist", "technologist", "ethicist",
    "environmentalist", "policy_analyst", "psychologist",
    "urban_planner", "healthcare_specialist", "education_expert",
    "security_analyst", "labor_economist", "demographer",
    "international_relations", "legal_scholar",
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


async def _select_expert_types(theme: str, stance_dist: dict, max_experts: int) -> list[str]:
    """LLM を使ってテーマに最適な専門家タイプを選出する。"""
    multi_llm_client.initialize()

    available = ", ".join(EXTENDED_EXPERT_POOL)
    system_prompt = (
        "あなたは議論パネルの構成アドバイザーです。\n"
        "テーマとスタンス分布を見て、最も有意義な議論に貢献できる専門家タイプを選んでください。\n\n"
        f"利用可能な専門家タイプ: {available}\n\n"
        f"出力はJSON形式のみ:\n"
        f'{{"experts": ["type1", "type2", ...], "reasoning": "選出理由"}}'
    )
    user_prompt = (
        f"テーマ: {theme}\n"
        f"スタンス分布: {stance_dist}\n"
        f"選出数: {max_experts}人\n\n"
        f"テーマに最も関連性が高く、多角的な議論を生む専門家の組み合わせを選んでください。"
    )

    try:
        result, _ = await multi_llm_client.call(
            provider_name="openai",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=512,
        )
        if isinstance(result, dict):
            experts = result.get("experts", [])
            # バリデーション: 存在するタイプのみ
            valid = [e for e in experts if e in EXTENDED_EXPERT_POOL]
            if valid:
                logger.info("LLM selected experts for '%s': %s", theme[:30], valid[:max_experts])
                return valid[:max_experts]
    except Exception as e:
        logger.warning("Expert type selection failed, using defaults: %s", e)

    return EXPERT_PERSONAS[:max_experts]


def _generate_dynamic_expert_template(persona_name: str) -> dict:
    """テンプレートが存在しない専門家タイプの動的テンプレートを生成する。"""
    display_names = {
        "psychologist": "心理学者",
        "urban_planner": "都市計画家",
        "healthcare_specialist": "医療専門家",
        "education_expert": "教育学者",
        "security_analyst": "安全保障アナリスト",
        "labor_economist": "労働経済学者",
        "demographer": "人口統計学者",
        "international_relations": "国際関係専門家",
        "legal_scholar": "法学者",
    }
    display_name = display_names.get(persona_name, persona_name)

    return {
        "display_name": display_name,
        "persona": {
            "role": display_name,
            "focus": f"{display_name}としての専門的視点",
            "thinking_style": "エビデンスベースで構造的",
        },
        "prompts": {
            "analyze": (
                f"あなたは{display_name}です。{display_name}としての専門的知見に基づいて、"
                f"このテーマを分析し、他の参加者が見落としている視点を提供してください。"
                f"具体的なデータや事例を引用して議論してください。"
            ),
        },
    }


async def select_representatives(
    agents: list[dict],
    responses: list[dict],
    max_citizen_reps: int = 6,
    max_experts: int = 4,
    theme: str = "",
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
    # _failed レスポンスを除外
    valid_pairs = [
        (a, r) for a, r in zip(agents, responses)
        if not r.get("_failed")
    ]
    if not valid_pairs:
        logger.error("No valid responses for representative selection, using all responses")
        valid_pairs = list(zip(agents, responses))

    valid_agents, valid_responses = zip(*valid_pairs) if valid_pairs else ([], [])
    clusters = _cluster_by_stance(list(valid_agents), list(valid_responses))

    # 非中立スタンスを優先（多様性保証）
    non_neutral_clusters = {k: v for k, v in clusters.items() if k != "中立"}
    neutral_cluster = clusters.get("中立", [])

    # まず非中立スタンスから選出
    citizen_count = 0
    if non_neutral_clusters:
        per_cluster = max(1, max_citizen_reps // max(len(non_neutral_clusters), 1))
        for stance, pairs in sorted(non_neutral_clusters.items(), key=lambda x: len(x[1]), reverse=True):
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

    # 残り枠を中立から補充（confidence が高い順）
    if citizen_count < max_citizen_reps and neutral_cluster:
        sorted_neutral = sorted(neutral_cluster, key=lambda x: x[1].get("confidence", 0.5), reverse=True)
        for agent, resp in sorted_neutral:
            if citizen_count >= max_citizen_reps:
                break
            participants.append({
                "agent_profile": agent,
                "response": resp,
                "role": "citizen_representative",
                "expertise": "",
                "stance": "中立",
            })
            citizen_count += 1

    # 全て中立しかない場合（Phase 1 修正後はレアケース）: confidence 分散で選出
    if citizen_count == 0:
        all_pairs = []
        for pairs in clusters.values():
            all_pairs.extend(pairs)
        sorted_all = sorted(all_pairs, key=lambda x: abs(x[1].get("confidence", 0.5) - 0.5), reverse=True)
        for agent, resp in sorted_all[:max_citizen_reps]:
            participants.append({
                "agent_profile": agent,
                "response": resp,
                "role": "citizen_representative",
                "expertise": "",
                "stance": resp.get("stance", "中立"),
            })
            citizen_count += 1

    # === 専門家の追加 ===
    # LLMベースでテーマに最適な専門家を選出
    stance_dist = {}
    for r in responses:
        s = r.get("stance", "中立")
        stance_dist[s] = stance_dist.get(s, 0) + 1
    total_resp = len(responses) or 1
    stance_dist = {k: v / total_resp for k, v in stance_dist.items()}

    if theme:
        selected_experts = await _select_expert_types(theme, stance_dist, max_experts)
    else:
        selected_experts = EXPERT_PERSONAS[:max_experts]

    for persona_name in selected_experts:
        template = _load_expert_template(persona_name)
        if not template:
            # テンプレートが無い場合は動的生成
            template = _generate_dynamic_expert_template(persona_name)
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
