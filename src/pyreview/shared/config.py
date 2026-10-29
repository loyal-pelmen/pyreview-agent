from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LlmConfig(_Strict):
    provider: Literal["gigachat"]
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)


class LintersConfig(_Strict):
    ruff: bool
    ty: bool
    timeout_seconds: float = Field(gt=0)
    ruff_select: tuple[str, ...] = Field(min_length=1)


class LimitsConfig(_Strict):
    max_file_bytes: int = Field(gt=0)
    max_findings: int = Field(gt=0)
    max_tool_calls: int = Field(gt=0)
    analysis_timeout_seconds: float = Field(gt=0)
    max_prompt_chars: int = Field(gt=0)
    max_tool_output_chars: int = Field(gt=0)
    max_lint_issues: int = Field(gt=0)


class AppConfig(_Strict):
    llm: LlmConfig
    linters: LintersConfig
    limits: LimitsConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    config_path: Path = Path("config.json")
    log_level: str = "INFO"
    gigachat_credentials: SecretStr | None = None
    gigachat_scope: str | None = None
    gigachat_ca_bundle_file: str | None = None


def load_config(path: Path) -> AppConfig:
    return AppConfig.model_validate_json(path.read_text(encoding="utf-8"))
