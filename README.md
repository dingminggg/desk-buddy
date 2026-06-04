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

## 与 Claude Code 联动（权限确认提醒）

让 Claude Code 需要你批准某个操作时，桌宠青蛙弹出提醒把你喊回来；你在终端
答复、Claude 继续或本回合结束后，提醒自动收起。

1. 先装好本包（开发模式）：`.venv\Scripts\python.exe -m pip install -e .`
2. 注册 hooks：`.venv\Scripts\python.exe -m desk_buddy.install_hooks`
   - 幂等地把三条 hook 写进 `~/.claude/settings.json`
     （`Notification`/`Stop`/`UserPromptSubmit`），不影响你已有配置。
   - 命令里写的是当前 venv 的 Python 绝对路径。
3. 重启 Claude Code 使 hooks 生效。
4. 保持 desk-buddy 运行即可。仅在「权限确认」时提醒；铃声最多响 3 次。

信号文件位于 `~/.claude/data/desk-buddy/pending/`，按会话分文件，支持同时开多个
Claude Code 会话。桌宠未运行时 hook 静默退出，不影响 Claude Code。
