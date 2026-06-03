from datetime import datetime

from pydantic import ValidationError

from .llm.base import LLMProvider
from .models import Intent, IntentAction

SYSTEM_TEMPLATE = """你是桌面提醒助手的解析器。当前时间是 {now}（请据此把相对时间换算成绝对时间）。
把用户的话解析为一个 JSON 对象，只输出 JSON，不要任何多余文字：
{{"action": "<add|query|complete|cancel|clarify>", "time": "<ISO8601 本地时间或 null>", "text": "<字符串>"}}

规则：
- 用户要新建提醒 -> action=add，time 填绝对时间（如 2026-06-04T15:00:00），text 填事项内容。
- 用户问有哪些提醒 -> action=query。
- 用户说某事做完了 -> action=complete，text 填能匹配该提醒的关键词。
- 用户要取消某提醒 -> action=cancel，text 填关键词。
- 时间含糊说不清或意图不明 -> action=clarify，text 填你要反问用户的话。
只返回 JSON。"""

CLARIFY_FALLBACK = "抱歉，我没太听懂，能换个说法再告诉我一次吗？"


class Brain:
    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def parse(self, text: str, now: datetime) -> Intent:
        system = SYSTEM_TEMPLATE.format(now=now.isoformat())
        raw = self._provider.chat(system, text)
        intent = self._try_parse(raw)
        if intent is not None:
            return intent

        # Retry once with explicit error feedback appended to the user turn.
        retry_user = (text + "\n\n上次没有返回合法 JSON，请严格只输出符合格式的 JSON。")
        raw = self._provider.chat(system, retry_user)
        intent = self._try_parse(raw)
        if intent is not None:
            return intent

        return Intent(action=IntentAction.CLARIFY, text=CLARIFY_FALLBACK)

    @staticmethod
    def _try_parse(raw: str) -> Intent | None:
        try:
            json_str = Brain._extract_json(raw)
            return Intent.model_validate_json(json_str)
        except (ValueError, ValidationError):
            return None

    @staticmethod
    def _extract_json(raw: str) -> str:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("no JSON object found")
        return raw[start:end + 1]
