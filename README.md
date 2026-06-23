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

The exe lands in `dist\desk-buddy.exe`. It's a single self-contained file —
copy it to any Windows machine and double-click; no Python install needed.
The build bundles the frog animation, the default reminder sound
(`guagua.mp3`), and the QtMultimedia + FFmpeg backend that plays it, so sound
works out of the box. (`desk_buddy.spec` builds from `launch.py`, which imports
the `desk_buddy` package properly — running `main.py` directly as the entry
script would break its relative imports.)

First launch still prompts for the API config; each machine keeps its own
`config.json` / `reminders.db` under `%APPDATA%\desk-buddy\`.

## Usage

Click the pet, type things like:
- 明天下午3点提醒我开会
- 我今天还有啥提醒
- 开会那个做完了
- 取消开会那个

不是提醒的话，桌宠会直接回答你（翻译、简单问答）——答案显示在桌宠头顶那张卡上
（和提醒共用），点「ok」关闭。例如：
- 把“你好”翻译成英文
- 法国的首都是哪

Reminders fire only while the app is running; on startup it catches up any that
came due while it was closed.

## 提醒声音

- **默认**：内置咕咕声（`src/desk_buddy/assets/guagua.mp3`，随包发布，开箱即用，
  无需配置）。
- **换成自己的**：右键宠物 →「设置」→「提示音」填 mp3/wav 路径（或点「浏览…」
  选文件），留空即用内置默认音。优先级：自定义文件 > 内置咕咕 > 系统叮声。
- **静音**：在设置里取消勾选「提醒时播放声音」。
- 提醒只用桌宠自己的气泡/卡片提示，不再弹 Windows 系统横幅通知。

## 与 Claude Code 联动

「权限确认提醒」已迁出本项目，改由 claude-cockpit(驾驶舱)自己的 hook 负责
(它有独立的提示音/信封/托盘提醒)。desk-buddy 现在专注做提醒小助手,不再
读写 Claude Code 的权限信号,也不再需要注册任何 hook。
