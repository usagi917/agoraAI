"""代表者選出: 活性化結果からスタンス別クラスタリング→代表者+専門家選出"""

import logging
import uuid
from collections import defaultdict

from src.app.services.society.age_utils import age_bracket_4 as _age_bracket

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
        stance = _resolved_stance(resp)
        clusters[stance].append((agent, resp))
    return clusters


def _resolved_stance(resp: dict | None) -> str:
    """伝播後スタンスがあればそれを優先して使う。"""
    if not resp:
        return "中立"
    return resp.get("propagated_stance") or resp.get("stance") or "中立"


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
                    "stance": _resolved_stance(resp),
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
                "stance": _resolved_stance(resp),
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
                "stance": _resolved_stance(resp),
            })
            citizen_count += 1

    # === 多様性制約（年齢帯・地域・性別）===
    # 既に選出済みの市民代表エージェントIDを追跡
    selected_agent_ids = {
        p["agent_profile"].get("id")
        for p in participants
        if p["role"] == "citizen_representative"
    }

    # 未選出エージェントを confidence 高い順にソートしたプール
    remaining_pool = sorted(
        [
            (a, r) for a, r in zip(valid_agents, valid_responses)
            if a.get("id") not in selected_agent_ids
        ],
        key=lambda x: x[1].get("confidence", 0.5),
        reverse=True,
    )

    def _current_citizens() -> list[dict]:
        return [p for p in participants if p["role"] == "citizen_representative"]

    def _swap_or_add(candidate_agent: dict, candidate_resp: dict) -> None:
        """候補を市民代表として追加 or 最低 confidence の代表と入れ替える。"""
        new_entry = {
            "agent_profile": candidate_agent,
            "response": candidate_resp,
            "role": "citizen_representative",
            "expertise": "",
            "stance": _resolved_stance(candidate_resp),
        }
        current = _current_citizens()
        if len(current) < max_citizen_reps:
            participants.append(new_entry)
        else:
            # confidence 最小の市民代表と入れ替え
            weakest = min(
                current,
                key=lambda p: p["response"].get("confidence", 0.5) if p["response"] else 0.0,
            )
            idx = participants.index(weakest)
            selected_agent_ids.discard(weakest["agent_profile"].get("id"))
            participants[idx] = new_entry
        selected_agent_ids.add(candidate_agent.get("id"))

    def _current_age_brackets() -> set[str]:
        return {
            _age_bracket(p["agent_profile"]["demographics"]["age"])
            for p in _current_citizens()
            if p["agent_profile"].get("demographics", {}).get("age") is not None
        }

    def _current_regions() -> set[str]:
        return {
            p["agent_profile"]["demographics"]["region"]
            for p in _current_citizens()
            if p["agent_profile"].get("demographics", {}).get("region")
        }

    def _current_genders() -> set[str]:
        return {
            p["agent_profile"]["demographics"]["gender"]
            for p in _current_citizens()
            if p["agent_profile"].get("demographics", {}).get("gender")
        }

    def _ensure_age_brackets() -> None:
        current_brackets = _current_age_brackets()
        missing_brackets = {"18-29", "30-49", "50-69", "70+"} - current_brackets
        for bracket in sorted(missing_brackets):
            candidates = [
                (a, r) for a, r in remaining_pool
                if a.get("id") not in selected_agent_ids
                and a.get("demographics", {}).get("age") is not None
                and _age_bracket(a["demographics"]["age"]) == bracket
            ]
            if candidates:
                _swap_or_add(candidates[0][0], candidates[0][1])

    def _ensure_regions() -> None:
        current_regions = _current_regions()
        region_candidates = [
            (a, r) for a, r in remaining_pool
            if a.get("id") not in selected_agent_ids
            and a.get("demographics", {}).get("region") not in current_regions
        ]
        for a, r in region_candidates:
            current_regions = _current_regions()
            if len(current_regions) >= 3:
                break
            region = a["demographics"]["region"]
            if region not in current_regions:
                _swap_or_add(a, r)
                current_regions = _current_regions()

    def _ensure_genders() -> None:
        current_genders = _current_genders()
        for gender in sorted({"male", "female"} - current_genders):
            gender_candidates = [
                (a, r) for a, r in remaining_pool
                if a.get("id") not in selected_agent_ids
                and a.get("demographics", {}).get("gender") == gender
            ]
            if gender_candidates:
                _swap_or_add(gender_candidates[0][0], gender_candidates[0][1])
                current_genders = _current_genders()

    # --- 多様性制約を安定するまで再適用 ---
    seen_selections: set[tuple[str, ...]] = set()
    for _ in range(max(1, max_citizen_reps)):
        selection_snapshot = tuple(sorted(aid for aid in selected_agent_ids if aid))
        if selection_snapshot in seen_selections:
            break
        seen_selections.add(selection_snapshot)

        before_state = (
            frozenset(_current_age_brackets()),
            frozenset(_current_regions()),
            frozenset(_current_genders()),
        )
        _ensure_age_brackets()
        _ensure_regions()
        _ensure_genders()
        after_state = (
            frozenset(_current_age_brackets()),
            frozenset(_current_regions()),
            frozenset(_current_genders()),
        )
        if after_state == before_state:
            break

    current_brackets = _current_age_brackets()
    if len(current_brackets) < 3:
        logger.warning(
            "Cannot satisfy >=3 age brackets; population lacks diversity. Got: %s",
            current_brackets,
        )

    current_regions = _current_regions()
    if len(current_regions) < 3:
        logger.warning(
            "Cannot satisfy >=3 regions; population lacks diversity. Got: %s",
            current_regions,
        )

    current_genders = _current_genders()
    missing_genders = {"male", "female"} - current_genders
    for gender in sorted(missing_genders):
        logger.warning("Diversity fallback: no candidate for gender %s", gender)

    # === 専門家の追加 ===
    # LLMベースでテーマに最適な専門家を選出
    stance_dist = {}
    for r in responses:
        s = _resolved_stance(r)
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
