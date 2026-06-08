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

提醒卡片会显示是哪个会话在等确认——取该会话工作目录的项目名，例如
`🤖 desk-buddy 在等你确认`；多个会话同时等确认时合并显示，例如
`🤖 2 个会话在等你确认：browser-harness、desk-buddy`。多开 Claude Code 时一眼
就知道该回哪个窗口。（旧版 Claude Code 不传 `cwd` 时回退显示 `Claude Code`。）

信号文件位于 `~/.claude/data/desk-buddy/pending/`，按会话分文件，支持同时开多个
Claude Code 会话。桌宠未运行时 hook 静默退出，不影响 Claude Code。
