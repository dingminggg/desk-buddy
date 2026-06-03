from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ReminderStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    CANCELLED = "cancelled"


class RepeatRule(str, Enum):
    NONE = "none"
    DAILY = "daily"


class Reminder(BaseModel):
    id: int | None = None
    text: str
    due_at: datetime
    status: ReminderStatus = ReminderStatus.PENDING
    repeat: RepeatRule = RepeatRule.NONE
    created_at: datetime
    notified: bool = False


class IntentAction(str, Enum):
    ADD = "add"
    QUERY = "query"
    COMPLETE = "complete"
    CANCEL = "cancel"
    CLARIFY = "clarify"


class Intent(BaseModel):
    action: IntentAction
    time: datetime | None = None
    text: str | None = None
