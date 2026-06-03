from ..config import Config
from .base import LLMProvider
from .openai_compat import OpenAICompatibleProvider


def build_provider(config: Config) -> LLMProvider:
    if config.provider == "openai_compatible":
        return OpenAICompatibleProvider(
            config.base_url, config.model, config.api_key)
    raise ValueError(f"unknown LLM provider: {config.provider!r}")
