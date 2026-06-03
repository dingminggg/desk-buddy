# desk-buddy ⇄ Claude Code「等你确认」提醒 设计

> 日期：2026-06-03
> 状态：设计已确认，待转实现计划
> 关系：在 v1 桌宠基础上新增「当 Claude Code 需要权限确认时，桌宠提醒我」的交互

## 1. 背景与目标

用户常在 Claude Code 里编码，期间 Claude 想用需要批准的工具（运行命令、写文件等）时会弹**权限确认**并阻塞等待。人若离开屏幕，Claude 就一直卡着、白白浪费时间。

目标：**当且仅当 Claude Code 需要权限确认时**，桌面常驻的青蛙桌宠弹出提醒把人喊回来；人回到终端答复、Claude 继续后，桌宠提醒自动收起。

**已确认决策**
- **触发**：只在「权限确认」时（不抓「空闲等待」类通知）。
- **强度**：视觉提醒一直挂着，直到「自动收起」或手动点掉；铃声首次 + 每 30 秒一次、**最多 3 声**封顶，之后只剩静默气泡。
- **自动收起灵敏度**：在**回合结束（Stop）/ 下一次用户输入（UserPromptSubmit）**时收起（方案 i）。不在 `PostToolUse` 上挂钩，避免给 Claude Code 每次工具调用增加 Python 启动开销。残留的静默气泡可手动点「知道了」立即消除。
- **IPC**：文件信号 + 桌宠轮询（方案 A），不开端口、不起网络服务。
- **安装**：`python -m desk_buddy.install_hooks` 幂等写入 `~/.claude/settings.json`。

**非目标（YAGNI）**：不抓空闲等待通知；不做输入排队、不做提醒历史、不做 toast/声音以外的通道扩展；不改漫游/草稿/定点提醒既有逻辑（仅做必要的优先级协调）。

## 2. 数据流

```
Claude 想用需批准的工具
  → Notification hook 触发（message 含 "permission"）
     → 写 ~/.claude/data/desk-buddy/pending/<session_id>.json     （"在等确认"）
  → 用户在终端点 允许/拒绝，Claude 继续/结束本回合
     → Stop / UserPromptSubmit hook 触发 → 删除该 session 的 pending 文件（"已解决"）

desk-buddy（常驻 GUI）：每 ~1 秒扫 pending/ 目录
  目录非空 → 弹「🤖 Claude Code 在等你确认」提醒
  目录变空 → 自动收起该提醒
```

按 `session_id` 分文件，天然支持同时开多个 Claude Code 会话：各自独立、互不串台。桌宠未运行时 hook 仍正常退出（只是没人消费）；桌宠启动时清理陈旧（>10 分钟）文件，避免显示过期提醒。

## 3. 信号层（`src/desk_buddy/cc_signals.py`，纯函数、可单测）

约定目录：`~/.claude/data/desk-buddy/pending/`。

- `pending_dir() -> Path`：返回目录路径（与 agent_pet 的 `~/.claude/data/...` 习惯一致）。
- `_safe_name(session_id) -> str`：仅保留 `[A-Za-z0-9_-]`，其余替换为 `_`，防目录穿越/非法文件名。
- `write_pending(session_id, message="") -> None`：原子写（tempfile + `os.replace`）`pending/<safe>.json`，内容 `{"session_id":..., "message":..., "at": <iso>}`。`mkdir(parents=True, exist_ok=True)`。
- `clear_pending(session_id) -> None`：删除对应文件；不存在则静默忽略。
- `read_pending() -> set[str]`：返回当前 pending 的 session_id 集合（目录不存在 → 空集；忽略读不动/坏文件）。
- `prune_stale(max_age_seconds=600) -> None`：删除 mtime 早于阈值的文件（启动期清理）。注意：时间戳由调用方/系统提供（脚本可用 `datetime.now`；桌宠侧用文件 mtime，不依赖被禁用的 `Date.now` 等）。

所有读操作对缺失/损坏文件**容错**（参考 agent_pet `state.load` 的健壮性）。

## 4. Hook 脚本（`src/desk_buddy/hooks/`）

均为独立脚本，被 Claude Code 以命令方式拉起；读 stdin 的 hook JSON（字段含 `session_id`、`hook_event_name`、`message` 等）。因 desk_buddy 以 `pip install -e` 装入 venv，用 `python -m desk_buddy.hooks.xxx` 调用即可 import，无需路径 hack。所有脚本：异常**只打 stderr 且返回 0**，绝不阻断 Claude Code。

- `hooks/notify.py`（绑 `Notification`）：解析 stdin；**仅当** `"permission" in message.lower()` 时 `cc_signals.write_pending(session_id, message)`。其它通知（如空闲等待）直接忽略 → 精确实现「只在权限确认时」。
- `hooks/clear.py`（绑 `Stop` 与 `UserPromptSubmit`）：解析 stdin；`cc_signals.clear_pending(session_id)`。

> 命中判据说明：Claude Code 的 Notification 负载无结构化「类型」字段，只能按 `message` 文案区分；权限通知文案含 "permission"（英文）。这是已知启发式，若 CC 文案变更需同步调整。

## 5. 桌宠端表现

### 5.1 `pet_widget.py`
- `show_alert(text, *, kind="reminder")`：现有持久卡新增 `kind` 形参，用于区分样式/图标（CC 用 🤖 前缀；默认仍是定点提醒）。`kind` 也供 App 端判定当前卡归属。
- 新增 `hide_alert()`：以编程方式收起当前提醒卡（停 nag 计时器、隐藏卡片），供「自动收起」调用。手动点「知道了」仍发 `alert_dismissed` 信号。

### 5.2 `app.py` — 新增 CC 提醒通道
- 状态：`self._cc_pending: bool`（或 session 集合）、`self._alert_kind`（当前卡是 `reminder` / `cc` / `None`）、`self._cc_ring_count: int`。
- `update_cc_pending(pending: bool) -> None`（由 main 的轮询每秒调用，传入「pending 目录是否非空」）：
  - `False → True`（出现待确认）：若当前**没有定点提醒**在显示 → 展示 CC 卡（`pet.show_alert(..., kind="cc")` + toast），`_cc_ring_count=1` 并响 1 声（若 `sound_enabled`）。若定点提醒正占用 → 仅记下 pending，待定点提醒关闭后再补弹。
  - `True → False`（已解决/清空）：若当前显示的是 CC 卡 → `pet.hide_alert()` 自动收起；清 CC 状态。若 CC 还在排队未弹 → 丢弃。
- `on_alert_nag()`（复用现有 30 秒 nag）：
  - 当前卡是 CC 且 `_cc_ring_count < 3` → 响铃、`_cc_ring_count += 1`；达到 3 后不再响（气泡仍在）。
  - 当前卡是定点提醒 → 维持现有「持续响」行为不变。
- `on_alert_dismissed()`（用户手动点「知道了」）：清当前卡状态；随后若 CC 仍 pending 且无定点提醒排队 → 补弹 CC；定点提醒队列照常推进。
- **优先级**：定点提醒（用户既有的「绝不能漏、必须手动关」）高于 CC 提醒。两者复用同一张持久卡（单槽位）；App 用 `_alert_kind` 记账，确保「自动收起」只作用于 CC 卡、不会误关定点提醒。

> 线程/Qt 解耦：App 保持无 Qt，所有方法在主线程被调用；轮询在 main 的 QTimer 里做（见 6）。

## 6. main 接线（`main.py`）
- 启动时 `cc_signals.prune_stale()` 清陈旧文件。
- 新增一个 ~1 秒 QTimer：`controller.update_cc_pending(bool(cc_signals.read_pending()))`。（与既有 scheduler tick 计时器分开，避免改动调度节奏。）
- 其余不变。

## 7. 一键安装（`src/desk_buddy/install_hooks.py`）
- `python -m desk_buddy.install_hooks`：
  - 读取（或新建）`~/.claude/settings.json`。
  - 在 `hooks` 段**幂等**登记三项：`Notification → notify`、`Stop → clear`、`UserPromptSubmit → clear`；命令用安装时的 `sys.executable` 绝对路径 + `-m desk_buddy.hooks.xxx`，保证指向 venv 内 Python。
  - 已存在等价条目则跳过，不破坏用户其它 hooks/配置；写入前备份原文件、原子写。
  - 打印结果摘要与卸载提示。
- README 增「与 Claude Code 联动」一节：先 `pip install -e .`，再 `python -m desk_buddy.install_hooks`，需重启 Claude Code 使 hooks 生效。

## 8. 测试
- `cc_signals`：write→read→clear 往返；坏/缺文件容错；`prune_stale` 按 mtime 删旧留新；`_safe_name` 过滤非法字符。
- `app`（用既有 fake pet/notifier；CC 通道用 SyncRunner 无关）：
  - pending `False→True` 且无定点提醒 → 弹 CC 卡 + 响 1 声。
  - pending `True→False` 且当前为 CC 卡 → 调 `hide_alert()`、状态清空。
  - nag：CC 卡铃声第 1/2/3 声响、第 4 次不响；定点提醒 nag 仍持续响。
  - 优先级：定点提醒占屏时 CC pending 不抢屏；定点提醒关闭后补弹；若期间 pending 清空则不补弹。
- `install_hooks`：写入临时 HOME 的 settings.json；首次写入三项；重复执行幂等（不重复、不破坏既有无关键）。
- hook 脚本（轻量）：喂一段权限 Notification JSON → 产生 pending 文件；喂空闲通知 → 不产生；喂 Stop/UserPromptSubmit → 清除。

## 9. 文件影响
| 文件 | 改动 |
|------|------|
| `src/desk_buddy/cc_signals.py` | 新增：pending 目录 + read/write/clear/prune/safe_name |
| `src/desk_buddy/hooks/__init__.py`、`hooks/notify.py`、`hooks/clear.py` | 新增：读 stdin → cc_signals |
| `src/desk_buddy/install_hooks.py` | 新增：幂等写 `~/.claude/settings.json` |
| `src/desk_buddy/app.py` | 新增 CC 提醒通道（update_cc_pending / 铃声封顶 / 优先级协调） |
| `src/desk_buddy/pet_widget.py` | `show_alert(kind=...)`、新增 `hide_alert()` |
| `src/desk_buddy/main.py` | 启动 `prune_stale()`；加 ~1s 轮询计时器 |
| `README.md` | 增「与 Claude Code 联动」安装说明 |
| `tests/test_cc_signals.py`、`tests/test_app.py`、`tests/test_install_hooks.py`、`tests/test_cc_hooks.py` | 对应测试 |

其余模块（models/config/store/scheduler/llm/brain/notify/qt_runner）不变。

## 10. 风险/注意
- **命中判据脆弱**：靠 Notification `message` 含 "permission" 区分权限 vs 空闲；CC 改文案会失效——集中在 `notify.py` 一处，易改。
- **PostToolUse 取舍**：方案 i 不挂 PostToolUse，故授权后静默气泡会挂到回合结束；以手动「知道了」兜底，铃声已封顶不扰人。
- **桌宠未运行**：hook 照常写文件并退出 0；陈旧文件由 `prune_stale` 在下次启动清理。
- **健壮性**：所有 hook 异常吞掉并返回 0，绝不阻断 Claude Code；信号读写对损坏文件容错。
- **跨进程时钟**：脚本侧用系统时间写 ISO 时间戳；桌宠侧 `prune_stale` 用文件 mtime，二者均不依赖被禁用的运行时时钟 API。
