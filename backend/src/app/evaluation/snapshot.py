"""実験スナップショット: git hash, パッケージバージョン, YAML設定の自動記録"""

import importlib.metadata
import logging
import subprocess
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.experiment_config import ExperimentConfig

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def capture_git_hash() -> str | None:
    """現在の git commit hash を取得する。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def capture_packages() -> dict[str, str]:
    """インストール済みパッケージのバージョンを取得する。"""
    try:
        return {
            dist.metadata["Name"].lower(): dist.version
            for dist in importlib.metadata.distributions()
            if dist.metadata["Name"]
        }
    except Exception:
        return {}


def capture_yaml_configs() -> dict[str, dict]:
    """YAML 設定ファイルをスナップショットする。"""
    config_files = {
        "models_yaml": "models.yaml",
        "cognitive_yaml": "cognitive.yaml",
        "graphrag_yaml": "graphrag.yaml",
        "llm_providers_yaml": "llm_providers.yaml",
    }
    result: dict[str, dict] = {}
    for key, filename in config_files.items():
        try:
            with open(CONFIG_DIR / filename) as f:
                result[key] = yaml.safe_load(f) or {}
        except (FileNotFoundError, yaml.YAMLError):
            result[key] = {}
    return result


async def save_experiment_snapshot(
    session: AsyncSession,
    simulation_id: str,
) -> ExperimentConfig:
    """シミュレーション開始時に実験設定スナップショットを保存する。"""
    git_hash = capture_git_hash()
    packages = capture_packages()
    yamls = capture_yaml_configs()

    config = ExperimentConfig(
        simulation_id=simulation_id,
        git_commit_hash=git_hash,
        python_packages=packages,
        models_yaml=yamls.get("models_yaml", {}),
        cognitive_yaml=yamls.get("cognitive_yaml", {}),
        graphrag_yaml=yamls.get("graphrag_yaml", {}),
        llm_providers_yaml=yamls.get("llm_providers_yaml", {}),
    )
    session.add(config)
    await session.commit()
    return config
