import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from pyreview.entrypoints.app import MULTIPART_OVERHEAD
from pyreview.shared.errors import (
    AnalysisTimeout,
    AppError,
    ModelUnavailable,
    NotUtf8,
    UnsupportedFile,
)
from tests.api.conftest import ClientFactory, FakeService

BROKEN_MULTIPART = "multipart/form-data; boundary=x"
PY = {"file": ("app.py", b"import os\nprint(1)\n", "text/x-python")}


async def test_healthz_ok_with_request_id(make_client: ClientFactory) -> None:
    async with make_client() as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_config_exposes_only_public_part(make_client: ClientFactory) -> None:
    async with make_client() as client:
        response = await client.get("/api/v1/config")
    assert response.json() == {
        "model": {"provider": "gigachat", "name": "GigaChat-2-Max"},
        "linters": ["ruff"],
        "limits": {"max_file_bytes": 100, "max_findings": 30, "analysis_timeout_seconds": 300},
    }
    assert "credentials" not in response.text


async def test_review_returns_contract_shape(make_client: ClientFactory) -> None:
    service = FakeService()
    async with make_client(service) as client:
        response = await client.post("/api/v1/review", files=PY)
    body = response.json()
    assert response.status_code == 200
    assert service.calls == [("app.py", b"import os\nprint(1)\n")]
    assert set(body) == {"file", "review", "lint", "reasoning", "model", "usage"}
    assert body["file"] == {"name": "app.py", "bytes": 19, "lines": 2}
    assert set(body["review"]) == {"verdict", "summary", "findings", "dropped"}
    assert body["review"]["findings"] == [
        {
            "line": 1,
            "end_line": None,
            "severity": "nit",
            "title": "Лишний импорт",
            "detail": "Не используется.",
            "suggestion": None,
        }
    ]
    assert body["lint"] == [
        {
            "tool": "ruff",
            "line": 1,
            "column": 8,
            "code": "F401",
            "message": "`os` imported but unused",
        }
    ]
    assert body["reasoning"] == [
        {"n": 1, "at_ms": 0, "kind": "thought", "text": "Посмотрю линтеры.", "truncated": False},
        {"n": 2, "at_ms": 10, "kind": "tool_call", "tool": "run_ruff", "args": {"path": "app.py"}},
        {
            "n": 3,
            "at_ms": 90,
            "kind": "tool_result",
            "text": "1:8 F401",
            "tool": "run_ruff",
            "truncated": False,
        },
        {"n": 4, "at_ms": 120, "kind": "conclusion", "text": "Лишний импорт.", "truncated": False},
    ]
    assert body["model"] == {"provider": "gigachat", "name": "GigaChat-2-Max"}
    assert body["usage"] == {"tokens": 100, "tool_calls": 1, "duration_ms": 150, "truncated": False}


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {},
        {"data": {"file": "не файл"}},
        {"files": [("file", ("a.py", b"1")), ("file", ("b.py", b"2"))]},
        {
            "content": b"--x\r\nbroken",
            "headers": {"content-type": "multipart/form-data; boundary=x"},
        },
    ],
)
async def test_review_without_single_file_is_unsupported(
    make_client: ClientFactory, request_kwargs: dict
) -> None:
    service = FakeService()
    async with make_client(service) as client:
        response = await client.post("/api/v1/review", **request_kwargs)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_file"
    assert service.calls == []


async def test_review_too_large_skips_service(make_client: ClientFactory) -> None:
    service = FakeService()
    async with make_client(service) as client:
        response = await client.post("/api/v1/review", files={"file": ("a.py", b"x" * 101)})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"
    assert service.calls == []


async def test_review_rejects_large_content_length_early(make_client: ClientFactory) -> None:
    service = FakeService()
    async with make_client(service) as client:
        response = await client.post(
            "/api/v1/review",
            content=b"x" * (100 + MULTIPART_OVERHEAD + 1),
            headers={"content-type": BROKEN_MULTIPART},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"
    assert service.calls == []


async def test_review_stops_reading_streamed_body_over_bound(make_client: ClientFactory) -> None:
    service = FakeService()
    sent = 0

    async def body() -> AsyncIterator[bytes]:
        nonlocal sent
        yield b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.py"\r\n\r\n'
        for _ in range(1000):
            sent += 1
            yield b"x" * 4096

    async with make_client(service) as client:
        response = await client.post(
            "/api/v1/review", content=body(), headers={"content-type": BROKEN_MULTIPART}
        )
    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"
    assert sent < 1000
    assert service.calls == []


async def test_review_rejects_long_text_field(make_client: ClientFactory) -> None:
    service = FakeService()
    async with make_client(service) as client:
        response = await client.post("/api/v1/review", data={"note": "x" * 2048}, files=PY)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_file"
    assert service.calls == []


@pytest.mark.parametrize(
    "error", [UnsupportedFile(), NotUtf8(), ModelUnavailable(), AnalysisTimeout()]
)
async def test_review_maps_service_errors(make_client: ClientFactory, error: AppError) -> None:
    async with make_client(FakeService(error)) as client:
        response = await client.post("/api/v1/review", files=PY)
    assert response.status_code == error.status
    assert response.json() == {"error": {"code": error.code, "message": error.message}}
    assert "x-request-id" in response.headers


async def test_unknown_error_is_internal_envelope(make_client: ClientFactory) -> None:
    async with make_client(FakeService(RuntimeError("секрет"))) as client:
        response = await client.post("/api/v1/review", files=PY)
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal", "message": "Внутренняя ошибка сервиса."}
    }
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_static_index_served_without_cache(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("<h1>pyreview</h1>", encoding="utf-8")
    async with make_client(frontend_dir=tmp_path) as client:
        page = await client.get("/")
        health = await client.get("/healthz")
    assert page.status_code == 200
    assert page.text == "<h1>pyreview</h1>"
    assert page.headers["cache-control"] == "no-cache"
    assert health.json() == {"status": "ok"}


async def test_missing_frontend_keeps_api(make_client: ClientFactory, tmp_path: Path) -> None:
    async with make_client(frontend_dir=tmp_path / "absent") as client:
        page = await client.get("/")
        config = await client.get("/api/v1/config")
    assert page.status_code == 404
    assert page.json()["error"]["code"] == "not_found"
    assert config.status_code == 200
