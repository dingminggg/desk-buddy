# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See `README.md` for setup, run, test, and build commands. There is
no linter; `pytest` is the only check. Python 3.11+.

## Architecture

A PySide6 desktop pet (a frog) that turns plain-language input into reminders
(and answers translation / simple Q&A via a `chat` intent).

**`App` (`app.py`) is the central controller.** It takes all collaborators by
constructor injection — `config, store, brain, pet, notifier, runner` — with
`pet`/`notifier` duck-typed. This is the main testing seam: tests build `App`
with fakes and a `SyncRunner`, no Qt loop. Two flows meet here:

1. **Input → reminder:** `PetWidget.user_said` → `handle_user_text` →
   `Brain.parse` (off-thread via the runner) → `ReminderStore` → `pet.say(...)`.
2. **Due → alert card:** `Scheduler` fires `handle_reminder_due` to show a due
   reminder on the shared card.

**The alert-card arbitration is the subtle part.** One card shows either a due
reminder (`kind="reminder"`) or a chat answer (`kind="chat"`); state is
`_alert_kind`/`_alert_active`/`_due_queue`. Reminders queue and dismiss one at a
time. Change this carefully against `test_app.py` / `test_pet_alert.py`.

**Keep Qt at the edges.** `App` and the pure modules never import Qt; it lives in
`pet_widget.py`, `qt_runner.py`, `main.py`. The `runner` abstraction is the
boundary: `QtRunner` runs slow callables (the LLM) on a worker thread and
marshals the result back to the UI thread; `SyncRunner` runs inline for tests.

**Brain + LLM (`brain.py`, `llm/`):** `Brain.parse` asks an `LLMProvider` for a
strict `Intent` JSON (`add|query|complete|cancel|chat|clarify`), retries once on
bad JSON, then falls back to CLARIFY. `chat` (translation / Q&A) carries the
answer in `text`; `App` shows it on the shared alert card via
`pet.show_alert(text, kind="chat")` — a manually-closed, silent card that joins
the reminder arbitration (occupies the card, queues due reminders behind it,
requeues a preempted reminder, never rings). Providers sit behind the `LLMProvider` ABC via
the `build_provider` factory. An `LLMError` makes `App` stash the raw text as a
draft instead of losing it.

**Persistence & scheduling:** SQLite `reminders`/`drafts` tables (`store.py`,
`models.py`); `repeat=daily` rolls the due date forward, `notified` fires each
reminder once. `Scheduler.tick(now)` is pure Python — the caller (a `QTimer` in
`main.py`) owns time, and startup calls it once to catch reminders missed while
closed.

**Config (`config.py`):** pydantic `Config` saved to
`%APPDATA%\desk-buddy\config.json`; the API key lives only there, never in the
DB.

**Claude Code permission alerts moved out.** desk-buddy no longer reads or writes
Claude Code's permission signals — that's now claude-cockpit's job (it owns the
hooks and the `~/.claude/data/claude-cockpit/pending/` channel). desk-buddy is a
standalone reminder pet again.

## Gotchas

- **The pet is the anchor window.** `main.py` sets
  `setQuitOnLastWindowClosed(False)`; only the right-click 退出 menu quits.
- **Packaging entry is `launch.py`, not `main.py`** — so `desk_buddy` imports as
  a package. The build bundles `frog.gif`, `guagua.mp3`, and QtMultimedia/FFmpeg.
- **Sound priority (`notify.py`):** custom `sound_file` → bundled `guagua.mp3` →
  `winsound` beep; all playback errors swallowed.
- **User-facing strings are Chinese.**

Past feature specs/plans live in `docs/superpowers/specs/` and `.../plans/`.
