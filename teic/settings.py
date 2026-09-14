"""Configuration loading: config/default.toml merged with .env / environment overrides.

No secrets in code. OPENROUTER_API_KEY comes from the environment only.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.toml"


class DaemonSettings(BaseSettings):
    base_tempo_hz: float = 1.0
    idle_tempo_hz: float = 0.2
    max_tempo_hz: float = 10.0
    db_path: str = "data/teic.db"


class LLMSettings(BaseSettings):
    primary_model: str = "~deepseek/deepseek-v4-flash-latest"
    fallback_model: str = "inclusionai/ling-3.0-flash-vl:free"
    base_url: str = "https://openrouter.ai/api/v1"
    request_timeout_s: float = 30.0
    max_retries: int = 3
    backoff_base_s: float = 1.0


class ViabilitySettings(BaseSettings):
    monthly_budget_usd: float = 10.0
    harness_monthly_budget_usd: float = 5.0
    allow_actual_termination: bool = False
    termination_justification: str = ""


class ResearchSettings(BaseSettings):
    enabled: bool = False


class InterfaceSettings(BaseSettings):
    web_host: str = "127.0.0.1"
    web_port: int = 8420


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


class TomlConfigSource(PydanticBaseSettingsSource):
    """Reads config/default.toml as a settings source, lowest precedence."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        raise NotImplementedError

    def __call__(self) -> dict[str, Any]:
        return _load_toml(DEFAULT_CONFIG_PATH)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TEIC_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    daemon: DaemonSettings = Field(default_factory=DaemonSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    viability: ViabilitySettings = Field(default_factory=ViabilitySettings)
    research: ResearchSettings = Field(default_factory=ResearchSettings)
    interface: InterfaceSettings = Field(default_factory=InterfaceSettings)

    openrouter_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENROUTER_API_KEY")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSource(settings_cls),
            file_secret_settings,
        )


def load_settings() -> Settings:
    return Settings()
