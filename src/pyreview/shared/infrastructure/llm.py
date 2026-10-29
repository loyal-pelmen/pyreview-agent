import warnings

from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, register_harness_profile
from langchain_core.language_models import BaseChatModel
from langchain_gigachat import GigaChat

from pyreview.shared.config import LlmConfig, Settings

register_harness_profile(
    "giga", HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False))
)


def build_chat_model(llm: LlmConfig, settings: Settings) -> BaseChatModel:
    warnings.filterwarnings("ignore", message="GigaChat API does not support tool_choice='any'")
    credentials = settings.gigachat_credentials
    return GigaChat(
        model=llm.model,
        temperature=llm.temperature,
        max_tokens=llm.max_tokens,
        timeout=llm.timeout_seconds,
        credentials=credentials.get_secret_value() if credentials else None,
        scope=settings.gigachat_scope,
        ca_bundle_file=settings.gigachat_ca_bundle_file,
        allow_any_tool_choice_fallback=True,
        max_retries=2,
    )


async def close_chat_model(model: BaseChatModel) -> None:
    if isinstance(model, GigaChat):
        await model._client.aclose()
