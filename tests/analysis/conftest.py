import importlib

import pytest


@pytest.fixture(autouse=True, scope="session")
def harness_profile() -> None:
    importlib.import_module("pyreview.shared.infrastructure.llm")
