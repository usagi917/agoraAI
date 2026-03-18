from pathlib import Path

import yaml
from pydantic_settings import BaseSettings


_project_root = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    database_url: str = "postgresql+asyncpg://agentai:agentai@localhost:5432/agentai"
    redis_url: str = "redis://localhost:6379/0"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    config_dir: Path = _project_root / "config"
    templates_dir: Path = _project_root / "templates"
    data_dir: Path = _project_root / "data"

    # Swarm settings
    max_concurrent_colonies: int = 5
    llm_cache_ttl: int = 3600  # seconds

    # Cognitive settings
    cognitive_mode: str = "legacy"  # legacy / advanced
    max_active_agents: int = 100
    max_concurrent_agents: int = 30

    model_config = {"env_file": str(_project_root / ".env"), "extra": "ignore"}

    def load_model_config(self) -> dict:
        config_path = self.config_dir / "models.yaml"
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f)
        return {"default_model": self.llm_model, "tasks": {}}

    def load_graphrag_config(self) -> dict:
        config_path = self.config_dir / "graphrag.yaml"
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f)
            return data.get("graphrag", {})
        return {}

    def load_cognitive_config(self) -> dict:
        config_path = self.config_dir / "cognitive.yaml"
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f)
        return {}

    def load_communication_config(self) -> dict:
        config_path = self.config_dir / "cognitive.yaml"
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f)
            return data.get("communication", {})
        return {}

    def load_scheduling_config(self) -> dict:
        config_path = self.config_dir / "cognitive.yaml"
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f)
            return data.get("scheduling", {})
        return {}

    def load_rate_limit_config(self) -> dict:
        config_path = self.config_dir / "cognitive.yaml"
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f)
            return data.get("rate_limiting", {})
        return {}

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.database_url


settings = Settings()
