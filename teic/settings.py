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
    # `monthly_budget_usd` doubles as the ledger's starting reserve
    # (teic/embodiment/viability_budget.py) -- a session starts each month
    # with its full budget available, so there's no separate "starting
    # budget" field to drift out of sync with this one.
    monthly_budget_usd: float = 10.0
    harness_monthly_budget_usd: float = 5.0
    # Depletion-rate parameter: normalizes one tick's real LLM spend (read
    # from teic/llm/cost.py, never synthetic) into the RegisterState
    # burn_rate channel's 0..1 scale.
    max_burn_rate_usd_per_tick: float = 0.05
    # Replenishment action's fixed amount. Never applied automatically --
    # only an explicit effector call to ViabilityBudget.replenish() adds
    # this, which is the concrete mechanism behind "replenishment requires
    # action, not a silent top-up."
    replenishment_amount_usd: float = 2.0
    # Allostatic forecast horizon (interoception/allostasis.py), in ticks.
    forecast_horizon_ticks: int = 10
    allow_actual_termination: bool = False
    termination_justification: str = ""


class ResearchSettings(BaseSettings):
    enabled: bool = False


class InterfaceSettings(BaseSettings):
    web_host: str = "127.0.0.1"
    web_port: int = 8420
    # Phase 9 cp2: terminal TUI's unfiltered log tail depth (v1 has no
    # filter/search -- see phase9-plan.md's cp1 log-surface decision).
    tui_log_tail_rows: int = 200
    # Phase 9 cp3: fixed evidence file the on-demand B1-B4 probe panel reads
    # from -- B1-B4 take synthetic/replayed evidence, never a live daemon
    # (teic/harness/probes/behavioral.py's convention), so "on demand" means
    # running the probe functions against this file, not deriving evidence
    # from the live session.
    tui_probe_evidence_path: str = "config/tui_probe_evidence_sample.json"


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
