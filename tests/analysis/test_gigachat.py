import warnings
from pathlib import Path

from langchain.agents.structured_output import OutputToolBinding, ToolStrategy
from langchain_core.tools import tool
from langchain_gigachat import GigaChat
from langchain_gigachat.utils.function_calling import convert_to_gigachat_tool

from pyreview.analysis.application.schema import ReviewDraft
from pyreview.analysis.application.tools import build_tools
from pyreview.analysis.application.trace import Trace
from pyreview.ioc import build_service, close_service
from pyreview.shared.config import Settings
from pyreview.shared.infrastructure.llm import build_chat_model
from tests.fakes import CONFIG, FakeLinter


def test_tools_and_review_schema_are_gigachat_compatible() -> None:
    structured = OutputToolBinding.from_schema_spec(ToolStrategy(ReviewDraft).schema_specs[0])
    tools = build_tools([FakeLinter("ruff"), FakeLinter("ty")], Path(), "a.py", 100, Trace(0))
    names = [convert_to_gigachat_tool(t)["function"]["name"] for t in [*tools, structured.tool]]
    assert names == ["think", "run_ruff", "run_ty", "ReviewDraft"]
    assert convert_to_gigachat_tool(ReviewDraft)["function"]["description"]


def test_build_chat_model_uses_config_and_settings() -> None:
    settings = Settings(gigachat_credentials="key", gigachat_scope="GIGACHAT_API_PERS")
    model = build_chat_model(CONFIG.llm, settings)

    @tool
    def probe(x: int) -> int:
        """Проверочный инструмент."""
        return x

    with warnings.catch_warnings(record=True) as caught:
        model.bind_tools([probe], tool_choice="any")
    assert caught == []
    assert model.model_dump(include={"model", "temperature", "credentials", "scope"}) == {
        "model": CONFIG.llm.model,
        "temperature": CONFIG.llm.temperature,
        "credentials": "key",
        "scope": "GIGACHAT_API_PERS",
    }


async def test_service_shares_one_chat_model_and_closes_it() -> None:
    service = build_service(CONFIG, Settings(_env_file=None, gigachat_credentials="key"))
    model = service.model_factory()
    assert isinstance(model, GigaChat)
    assert service.model_factory() is model
    http = model._client._aclient

    await close_service(service)

    assert http.is_closed
