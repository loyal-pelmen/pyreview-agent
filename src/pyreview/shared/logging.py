from uuid import uuid4

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars
from structlog.tracebacks import ExceptionDictTransformer


def setup_logging(level: str) -> None:
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.ExceptionRenderer(ExceptionDictTransformer(show_locals=False)),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level.upper()),
        logger_factory=structlog.WriteLoggerFactory(),
    )


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex
        clear_contextvars()
        bind_contextvars(request_id=request_id)
        header = (b"x-request-id", request_id.encode())

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), header]
            await send(message)

        await self.app(scope, receive, send_with_id)
