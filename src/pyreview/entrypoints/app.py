import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

import structlog
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Message, Receive, Scope
from structlog.contextvars import get_contextvars

from pyreview.analysis.domain import ReviewReport
from pyreview.entrypoints.schemas import (
    ConfigResponse,
    ErrorBody,
    ErrorResponse,
    HealthResponse,
    ReviewResponse,
)
from pyreview.ioc import build_service, close_service, read_config
from pyreview.shared.config import AppConfig, Settings
from pyreview.shared.errors import AppError, FileTooLarge, UnsupportedFile
from pyreview.shared.logging import RequestIdMiddleware, setup_logging

FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
HTTP_ERRORS = {
    404: ("not_found", "Ресурс не найден."),
    405: ("method_not_allowed", "Метод не поддерживается."),
}
MULTIPART_OVERHEAD = 64 * 1024
MAX_TEXT_PART = 1024

log = structlog.get_logger()
probe = APIRouter()
api = APIRouter(prefix="/api/v1")


class Reviewer(Protocol):
    async def review(self, name: str, data: bytes) -> ReviewReport: ...


class NoCacheFiles(StaticFiles):
    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-cache"
        return response


def capped(receive: Receive, limit: int) -> Receive:
    received = 0

    async def counted() -> Message:
        nonlocal received
        message = await receive()
        received += len(message.get("body", b""))
        if received > limit:
            raise FileTooLarge
        return message

    return counted


def envelope(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message))
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


async def on_app_error(_: Request, exc: AppError) -> JSONResponse:
    log.info("request_rejected", status=exc.status, code=exc.code)
    return envelope(exc.status, exc.code, exc.message)


async def on_http_error(_: Request, exc: HTTPException) -> JSONResponse:
    if exc.status_code == UnsupportedFile.status:
        return await on_app_error(_, UnsupportedFile())
    code, message = HTTP_ERRORS.get(exc.status_code, ("bad_request", "Некорректный запрос."))
    return envelope(exc.status_code, code, message)


async def on_validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    return await on_app_error(_, UnsupportedFile())


async def on_unhandled(_: Request, __: Exception) -> JSONResponse:
    log.exception("request_failed")
    error = AppError()
    request_id = get_contextvars().get("request_id", "")
    return envelope(error.status, error.code, error.message, {"X-Request-Id": request_id})


@probe.get("/healthz")
async def healthz() -> HealthResponse:
    return HealthResponse()


@api.get("/config")
async def config(request: Request) -> ConfigResponse:
    return ConfigResponse.from_config(request.app.state.config)


@api.post("/review")
async def review(request: Request) -> ReviewResponse:
    limit = request.app.state.config.limits.max_file_bytes
    bound = limit + MULTIPART_OVERHEAD
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > bound:
        raise FileTooLarge
    limited = Request(request.scope, capped(request.receive, bound))
    async with limited.form(max_files=1, max_fields=1, max_part_size=MAX_TEXT_PART) as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise UnsupportedFile
        data = await upload.read(limit + 1)
    if len(data) > limit:
        raise FileTooLarge
    report: ReviewReport = await request.app.state.service.review(upload.filename or "", data)
    log.info(
        "review_done",
        bytes=report.file.size,
        lines=report.file.lines,
        model=report.model.name,
        tool_calls=report.usage.tool_calls,
        findings=len(report.review.findings),
        duration_ms=report.usage.duration_ms,
    )
    return ReviewResponse.model_validate(report)


def create_app(
    config: AppConfig | None = None,
    service: Reviewer | None = None,
    frontend_dir: Path = FRONTEND_DIR,
) -> FastAPI:
    owned = None
    if config is None or service is None:
        settings = Settings()
        setup_logging(settings.log_level)
        config = config or read_config(settings.config_path)
        if service is None:
            service = owned = build_service(config, settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        if owned is not None:
            await close_service(owned)

    app = FastAPI(
        title="pyreview",
        lifespan=lifespan,
        exception_handlers={
            AppError: on_app_error,
            HTTPException: on_http_error,
            RequestValidationError: on_validation_error,
            Exception: on_unhandled,
        },
    )
    app.state.config, app.state.service = config, service
    app.include_router(probe)
    app.include_router(api)
    app.add_middleware(RequestIdMiddleware)
    if (frontend_dir / "index.html").is_file():
        app.mount("/", NoCacheFiles(directory=frontend_dir, html=True), name="frontend")
    return app
