from pathlib import Path

import structlog
from pydantic import ValidationError

from pyreview.analysis.application.service import ReviewService
from pyreview.linters.application import Linter
from pyreview.linters.infrastructure.ruff import RuffLinter
from pyreview.linters.infrastructure.ty import TyLinter
from pyreview.shared.config import AppConfig, Settings, load_config
from pyreview.shared.infrastructure.llm import build_chat_model, close_chat_model

log = structlog.get_logger()


def read_config(path: Path) -> AppConfig:
    try:
        return load_config(path)
    except ValidationError as exc:
        fields = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
        log.error("config_invalid", path=str(path), fields=fields)
        raise
    except OSError as exc:
        log.error("config_unreadable", path=str(path), error=str(exc))
        raise


def build_service(config: AppConfig, settings: Settings) -> ReviewService:
    linters: list[Linter] = []
    if config.linters.ruff:
        linters.append(RuffLinter(config.linters.ruff_select, config.linters.timeout_seconds))
    if config.linters.ty:
        linters.append(TyLinter(config.linters.timeout_seconds))
    model = build_chat_model(config.llm, settings)
    return ReviewService(config, linters, lambda: model)


async def close_service(service: ReviewService) -> None:
    await close_chat_model(service.model_factory())
