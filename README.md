# desk-buddy

A Windows desktop floating pet (an animated frog) that turns plain-language requests into reminders.

## Develop

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -e ".[dev]"
    .venv\Scripts\python.exe -m pytest -q

## Run

    .venv\Scripts\python.exe -m desk_buddy.main

On first launch, enter an OpenAI-compatible `Base URL`, `Model`, and `API Key`
(works with OpenRouter, Groq, DeepSeek, Moonshot, local Ollama/LM Studio, etc.).
Config is saved to `%APPDATA%\desk-buddy\config.json`; the API key is never
written to the database.

## Build a standalone exe

    .venv\Scripts\python.exe -m pip install pyinstaller
    .venv\Scripts\pyinstaller.exe desk_buddy.spec

The exe lands in `dist\desk-buddy.exe`.

## Usage

Click the pet, type things like:
- 明天下午3点提醒我开会
- 我今天还有啥提醒
- 开会那个做完了
- 取消开会那个

Reminders fire only while the app is running; on startup it catches up any that
came due while it was closed.
