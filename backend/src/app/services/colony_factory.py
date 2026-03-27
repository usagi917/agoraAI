"""Colony Factory: Swarm プロファイルと視点設定から ColonyConfig を生成"""

import logging
import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ColonyConfig:
    colony_id: str
    simulation_id: str
    colony_index: int
    perspective_id: str
    perspective_label: str
    system_injection: str
    temperature: float
    prompt_variant: int
    model_override: str | None
    adversarial: bool
    round_count: int


def _load_perspectives() -> list[dict]:
    path = settings.config_dir / "perspectives.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("perspectives", [])


def _load_swarm_profiles() -> dict:
    path = settings.config_dir / "swarm_profiles.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("profiles", {})


def generate_colony_configs(
    simulation_id: str,
    profile_name: str,
    diversity_mode: str = "balanced",
) -> list[ColonyConfig]:
    """Swarm プロファイルに基づいて ColonyConfig リストを生成する。"""
    profiles = _load_swarm_profiles()
    profile = profiles.get(profile_name)
    if not profile:
        raise ValueError(f"Unknown swarm profile: {profile_name}")

    colony_count = profile["colony_count"]
    temperatures = profile["temperatures"]
    round_count = profile["round_count"]
    ensure_adversarial = profile.get("ensure_adversarial", True)

    perspectives = _load_perspectives()
    if not perspectives:
        raise ValueError("No perspectives configured")

    # 視点の選択
    selected = _select_perspectives(
        perspectives, colony_count, ensure_adversarial, diversity_mode,
    )

    configs = []
    for i, (perspective, temp) in enumerate(zip(selected, temperatures)):
        config = ColonyConfig(
            colony_id=str(uuid.uuid4()),
            simulation_id=simulation_id,
            colony_index=i,
            perspective_id=perspective["id"],
            perspective_label=perspective["label"],
            system_injection=perspective.get("system_injection", ""),
            temperature=temp,
            prompt_variant=i % 3,  # 3種のプロンプト変種をローテーション
            model_override=None,
            adversarial=perspective.get("adversarial", False),
            round_count=round_count,
        )
        configs.append(config)

    logger.info(
        f"Generated {len(configs)} colony configs for swarm {simulation_id} "
        f"(profile={profile_name}, diversity={diversity_mode})"
    )
    return configs


def _select_perspectives(
    perspectives: list[dict],
    count: int,
    ensure_adversarial: bool,
    diversity_mode: str,
) -> list[dict]:
    """多様性モードに応じて視点を選択する。"""
    adversarial = [p for p in perspectives if p.get("adversarial", False)]
    non_adversarial = [p for p in perspectives if not p.get("adversarial", False)]

    selected = []

    # 敵対的視点を確保
    if ensure_adversarial and adversarial:
        adv_pick = random.choice(adversarial)
        selected.append(adv_pick)
        count -= 1

    # 残りの視点を選択
    if diversity_mode == "maximum":
        # 全非敵対的視点からできるだけ多様に
        pool = list(non_adversarial)
        random.shuffle(pool)
        selected.extend(pool[:count])
    elif diversity_mode == "minimal":
        # 少数の代表的な視点
        core = [p for p in non_adversarial if p["id"] in (
            "institutional_conservative", "disruptive_innovation", "optimistic_growth",
        )]
        if not core:
            core = non_adversarial[:3]
        random.shuffle(core)
        selected.extend(core[:count])
    else:  # balanced
        pool = list(non_adversarial)
        random.shuffle(pool)
        selected.extend(pool[:count])

    # 足りない場合はランダムに補充
    while len(selected) < count + (1 if ensure_adversarial and adversarial else 0):
        selected.append(random.choice(perspectives))

    return selected
