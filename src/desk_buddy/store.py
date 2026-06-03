import sqlite3
from datetime import datetime, timedelta

from .models import Reminder, ReminderStatus, RepeatRule

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    repeat TEXT NOT NULL DEFAULT 'none',
    created_at TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class ReminderStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _row_to_reminder(self, row: sqlite3.Row) -> Reminder:
        return Reminder(
            id=row["id"],
            text=row["text"],
            due_at=datetime.fromisoformat(row["due_at"]),
            status=ReminderStatus(row["status"]),
            repeat=RepeatRule(row["repeat"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            notified=bool(row["notified"]),
        )

    def add(self, reminder: Reminder) -> Reminder:
        cur = self._conn.execute(
            "INSERT INTO reminders (text, due_at, status, repeat, created_at, notified)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (reminder.text, reminder.due_at.isoformat(), reminder.status.value,
             reminder.repeat.value, reminder.created_at.isoformat(),
             int(reminder.notified)),
        )
        self._conn.commit()
        reminder.id = cur.lastrowid
        return reminder

    def get(self, rid: int) -> Reminder | None:
        row = self._conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (rid,)).fetchone()
        return self._row_to_reminder(row) if row else None

    def list_active(self) -> list[Reminder]:
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending' ORDER BY due_at"
        ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def list_due(self, now: datetime) -> list[Reminder]:
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending' AND notified = 0"
            " AND due_at <= ? ORDER BY due_at",
            (now.isoformat(),),
        ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def search_active(self, keyword: str) -> list[Reminder]:
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending' AND text LIKE ?"
            " ORDER BY due_at",
            (f"%{keyword}%",),
        ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def complete(self, rid: int) -> None:
        self._conn.execute(
            "UPDATE reminders SET status = 'done' WHERE id = ?", (rid,))
        self._conn.commit()

    def cancel(self, rid: int) -> None:
        self._conn.execute(
            "UPDATE reminders SET status = 'cancelled' WHERE id = ?", (rid,))
        self._conn.commit()

    def mark_notified(self, rid: int) -> None:
        self._conn.execute(
            "UPDATE reminders SET notified = 1 WHERE id = ?", (rid,))
        self._conn.commit()

    def advance_daily(self, rid: int, now: datetime) -> None:
        reminder = self.get(rid)
        if reminder is None:
            return
        new_due = reminder.due_at
        while new_due <= now:
            new_due += timedelta(days=1)
        self._conn.execute(
            "UPDATE reminders SET due_at = ?, notified = 0 WHERE id = ?",
            (new_due.isoformat(), rid),
        )
        self._conn.commit()

    def save_draft(self, text: str) -> None:
        self._conn.execute(
            "INSERT INTO drafts (text, created_at) VALUES (?, ?)",
            (text, datetime.now().isoformat()),
        )
        self._conn.commit()

    def list_drafts(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT text FROM drafts ORDER BY id").fetchall()
        return [r["text"] for r in rows]
