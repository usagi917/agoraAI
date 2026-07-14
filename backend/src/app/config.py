import logging
import shlex
from pathlib import Path

import yaml
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def _resolve_project_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for candidate in current.parents:
        if (candidate / "config").is_dir() and (candidate / "templates").is_dir():
            return candidate
    return current.parents[min(3, len(current.parents) - 1)]


_project_root = _resolve_project_root()


class Settings(BaseSettings):
    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    database_url: str = "postgresql+asyncpg://agentai:agentai@localhost:5432/agentai"
    redis_url: str = "redis://localhost:6379/0"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    allowed_origins: str = ""
    config_dir: Path = _project_root / "config"
    templates_dir: Path = _project_root / "templates"
    data_dir: Path = _project_root / "data"
    codex_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("CODEX_REVIEW_ENABLED", "AGORAAI_CODEX_ENABLED"),
    )
    codex_command: str = Field(
        default="codex",
        validation_alias=AliasChoices("CODEX_BIN", "AGORAAI_CODEX_COMMAND"),
    )
    codex_args: str = Field(
        default="app-server --listen stdio://",
        validation_alias=AliasChoices("CODEX_REVIEW_ARGS", "AGORAAI_CODEX_ARGS"),
    )
    codex_review_transport: str = Field(default="stdio", validation_alias="CODEX_REVIEW_TRANSPORT")
    codex_timeout_seconds: float = Field(
        default=60.0,
        validation_alias=AliasChoices("CODEX_REVIEW_TIMEOUT_SECONDS", "AGORAAI_CODEX_TIMEOUT_SECONDS"),
    )
    codex_startup_timeout_seconds: float = Field(
        default=10.0,
        validation_alias=AliasChoices("CODEX_REVIEW_STARTUP_TIMEOUT_SECONDS", "AGORAAI_CODEX_STARTUP_TIMEOUT_SECONDS"),
    )
    codex_review_model: str = Field(default="", validation_alias="CODEX_REVIEW_MODEL")
    codex_review_mock: bool = Field(default=False, validation_alias="CODEX_REVIEW_MOCK")
    codex_review_max_context_chars: int = Field(default=24000, validation_alias="CODEX_REVIEW_MAX_CONTEXT_CHARS")
    codex_review_workdir: Path = Field(
        default=Path("/tmp/agora_codex_review_empty"),
        validation_alias="CODEX_REVIEW_WORKDIR",
    )
    codex_review_only: bool = Field(
        default=True,
        validation_alias=AliasChoices("CODEX_REVIEW_ONLY", "AGORAAI_CODEX_REVIEW_ONLY"),
    )
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
                return yaml.safe_load(f) or {}
        return {"default_model": self.llm_model, "tasks": {}}

    def llm_provider(self) -> str:
        return self.load_model_config().get("provider", "openai")

    def live_simulation_available(self) -> bool:
        return self.llm_provider() != "openai" or bool(self.openai_api_key)

    def live_simulation_message(self) -> str:
        if self.live_simulation_available():
            return "Live simulation is available."
        if self.llm_provider() == "openai":
            return "OPENAI_API_KEY is not configured. Sample results are still available."
        return f"LLM provider '{self.llm_provider()}' is not available."

    def cors_origins(self) -> list[str]:
        raw = (self.allowed_origins or "").strip()
        if not raw:
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    def codex_argv(self) -> list[str]:
        return [self.codex_command, *shlex.split(self.codex_args)]

    def codex_transport_supported(self) -> bool:
        return self.codex_review_transport.strip().lower() == "stdio"

    def load_graphrag_config(self) -> dict:
        config_path = self.config_dir / "graphrag.yaml"
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            return data.get("graphrag", {})
        return {}

    def load_cognitive_config(self) -> dict:
        config_path = self.config_dir / "cognitive.yaml"
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def load_communication_config(self) -> dict:
        config_path = self.config_dir / "cognitive.yaml"
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            return data.get("communication", {})
        return {}

    def load_scheduling_config(self) -> dict:
        config_path = self.config_dir / "cognitive.yaml"
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            return data.get("scheduling", {})
        return {}

    def load_rate_limit_config(self) -> dict:
        config_path = self.config_dir / "cognitive.yaml"
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            return data.get("rate_limiting", {})
        return {}

    def load_llm_providers_config(self) -> dict:
        config_path = self.config_dir / "llm_providers.yaml"
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        return {"providers": {}, "fallback_order": []}

    def load_population_mix_config(self) -> dict:
        config_path = self.config_dir / "population_mix.yaml"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    return yaml.safe_load(f) or {}
            except (yaml.YAMLError, OSError) as e:
                logger.error("Failed to load population_mix.yaml: %s", e)
                return {}
        return {}

    def load_hybrid_inference_config(self) -> dict:
        config_path = self.config_dir / "hybrid_inference.yaml"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    return yaml.safe_load(f) or {}
            except (yaml.YAMLError, OSError) as exc:
                logger.error("Failed to load hybrid_inference.yaml: %s", exc)
        return {}

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.database_url


settings = Settings()
