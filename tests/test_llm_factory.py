import pytest

from desk_buddy.config import Config
from desk_buddy.llm import build_provider
from desk_buddy.llm.openai_compat import OpenAICompatibleProvider


def test_builds_openai_compatible_provider():
    cfg = Config(provider="openai_compatible", base_url="https://x/v1",
                 model="m", api_key="sk-1")
    provider = build_provider(cfg)
    assert isinstance(provider, OpenAICompatibleProvider)


def test_unknown_provider_raises():
    cfg = Config(provider="banana", base_url="https://x/v1",
                 model="m", api_key="sk-1")
    with pytest.raises(ValueError):
        build_provider(cfg)
