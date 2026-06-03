import pytest
import requests

from desk_buddy.llm.base import LLMError
from desk_buddy.llm.openai_compat import OpenAICompatibleProvider


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_chat_posts_and_returns_content(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse(200, {"choices": [{"message": {"content": "hello"}}]})

    monkeypatch.setattr(requests, "post", fake_post)
    provider = OpenAICompatibleProvider("https://api.test/v1/", "gpt-x", "sk-1")
    out = provider.chat("sysprompt", "userprompt")

    assert out == "hello"
    assert captured["url"] == "https://api.test/v1/chat/completions"
    assert captured["json"]["model"] == "gpt-x"
    assert captured["json"]["messages"] == [
        {"role": "system", "content": "sysprompt"},
        {"role": "user", "content": "userprompt"},
    ]
    assert captured["headers"]["Authorization"] == "Bearer sk-1"


def test_chat_raises_llmerror_on_http_error(monkeypatch):
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: _FakeResponse(500, {"error": "boom"}))
    provider = OpenAICompatibleProvider("https://api.test/v1", "m", "sk-1")
    with pytest.raises(LLMError):
        provider.chat("s", "u")


def test_chat_raises_llmerror_on_network_failure(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(requests, "post", boom)
    provider = OpenAICompatibleProvider("https://api.test/v1", "m", "sk-1")
    with pytest.raises(LLMError):
        provider.chat("s", "u")
