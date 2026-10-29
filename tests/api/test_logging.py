from collections.abc import Iterator

import pytest
import structlog

from pyreview.shared.logging import setup_logging

MARKER = "секрет-маркер-7f3a"


@pytest.fixture(autouse=True)
def reset_structlog() -> Iterator[None]:
    yield
    structlog.reset_defaults()


def fail_with_secret(api_key: str) -> None:
    raise RuntimeError(len(api_key))


def test_exception_log_omits_frame_locals(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging("info")
    try:
        fail_with_secret(MARKER)
    except RuntimeError:
        structlog.get_logger().exception("request_failed")
    output = capsys.readouterr().out
    assert "request_failed" in output
    assert "fail_with_secret" in output
    assert MARKER not in output
