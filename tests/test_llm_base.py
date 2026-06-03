import pytest

from desk_buddy.llm.base import LLMProvider, LLMError


def test_provider_is_abstract():
    with pytest.raises(TypeError):
        LLMProvider()


def test_concrete_provider_can_chat():
    class Echo(LLMProvider):
        def chat(self, system: str, user: str) -> str:
            return f"{system}|{user}"

    assert Echo().chat("sys", "hi") == "sys|hi"


def test_llm_error_is_exception():
    assert issubclass(LLMError, Exception)
