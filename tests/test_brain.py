from datetime import datetime

from desk_buddy.brain import Brain
from desk_buddy.llm.base import LLMProvider
from desk_buddy.models import IntentAction


class ScriptedProvider(LLMProvider):
    """Returns queued replies; records the prompts it received."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def chat(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._replies.pop(0)


NOW = datetime(2026, 6, 3, 10, 0)


def test_parses_clean_json_add():
    p = ScriptedProvider(['{"action": "add", "time": "2026-06-04T15:00:00", "text": "开会"}'])
    intent = Brain(p).parse("明天下午3点提醒我开会", NOW)
    assert intent.action == IntentAction.ADD
    assert intent.time == datetime(2026, 6, 4, 15, 0)
    assert intent.text == "开会"


def test_parses_json_wrapped_in_code_fence():
    p = ScriptedProvider(['```json\n{"action": "query"}\n```'])
    intent = Brain(p).parse("我今天还有啥提醒", NOW)
    assert intent.action == IntentAction.QUERY


def test_current_time_injected_into_system_prompt():
    p = ScriptedProvider(['{"action": "query"}'])
    Brain(p).parse("查提醒", NOW)
    system_prompt = p.calls[0][0]
    assert "2026-06-03" in system_prompt


def test_retries_once_on_bad_json_then_succeeds():
    p = ScriptedProvider([
        "对不起我不会",                       # garbage, no JSON
        '{"action": "complete", "text": "开会"}',
    ])
    intent = Brain(p).parse("开会那个做完了", NOW)
    assert intent.action == IntentAction.COMPLETE
    assert len(p.calls) == 2  # retried once


def test_falls_back_to_clarify_after_two_failures():
    p = ScriptedProvider(["nonsense", "still nonsense"])
    intent = Brain(p).parse("???", NOW)
    assert intent.action == IntentAction.CLARIFY
    assert intent.text  # has a non-empty question
    assert len(p.calls) == 2


def test_parses_chat_answer():
    p = ScriptedProvider(['{"action": "chat", "text": "Bonjour"}'])
    intent = Brain(p).parse('把"你好"翻译成法语', NOW)
    assert intent.action == IntentAction.CHAT
    assert intent.text == "Bonjour"


def test_system_prompt_mentions_chat():
    p = ScriptedProvider(['{"action": "chat", "text": "x"}'])
    Brain(p).parse("法国的首都是哪", NOW)
    assert "chat" in p.calls[0][0]
