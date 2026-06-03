# desk-buddy 持久到点提醒 + 关漫游 设计

> 日期：2026-06-03
> 状态：设计已确认，待转实现计划
> 关系：在已交付的 v1（提醒器）基础上，改进「到点提醒」的呈现方式，并临时关闭自主漫游

## 1. 背景与目标

现状问题：
1. **到点提醒会被错过**。到点时用随手气泡 `pet.say()` 显示，6 秒后自动消失。重启补漏（`scheduler.tick(now)`）会把所有错过的提醒**同步**逐条 `handle_reminder_due`，气泡互相覆盖、提示音/toast 叠在一起，用户只看到最后一条。
2. **青蛙形象不适合自主漫游**，需要暂时关掉。

目标：
- **每条到点提醒用持久弹窗**：不自动消失，必须用户手动「知道了」关闭，以免错过。
- **同一时间只显示一条**；关掉一条自动弹出队列里的下一条（启动补漏的多条也这样逐一过）。
- 弹出时：持久弹窗 + Windows toast + 提示音；**未关闭期间每 30 秒重播一次提示音**催促。
- **临时关闭自主漫游**（漫游代码保留，便于以后再开）。

**已确认决策**
- 仅「到点提醒」用持久弹窗；随手确认/问候/反问仍用自动消失的 `say()` 气泡（用户输入时在看着，不会错过）。
- 「知道了」按钮只是**确认关闭**，不顺带把提醒标记为已完成（完成仍由用户说"做完了"走解析）。

非目标（YAGNI）：不做提醒历史面板、不做「稍后提醒/snooze」、不做按钮直接标记完成、不删除漫游能力（只是默认关）。

## 2. 组件：ReminderAlert（在 `PetWidget` 内）

新增一个**持久**提醒弹窗，与现有随手气泡 `say()`/`_bubble` 相互独立。

- 外观：沿用输入条的风格——透明顶层窗口内一张白色圆角卡片 + 柔和投影；内含：
  - 提醒文字 `QLabel`（自动换行），显示 `⏰ {reminder.text}`。
  - 一个「知道了」`QPushButton` 关闭按钮。
- 行为：
  - `show_alert(text)`：设置文字、定位在宠物附近（宠物正上方；越界则正下方）、显示；**不启动任何自动隐藏定时器**；启动 30s 催铃定时器。
  - 不自动消失。点「知道了」→ 隐藏、停催铃定时器、`alert_dismissed` 信号。
  - 催铃定时器（`QTimer`，间隔 `ALERT_NAG_MS = 30000`，循环）每次 timeout → `alert_nag` 信号。
- 信号：`alert_dismissed = Signal()`、`alert_nag = Signal()`。
- 拖动宠物时，弹窗跟随（与气泡/输入条一致，复用 `_position_*` 思路）。

`PetWidget` 公开方法新增 `show_alert(text)`；新增信号 `alert_dismissed`、`alert_nag`。`say()`/`_bubble`/`_bubble_timer`（6s 自动隐藏）保持不变。

## 3. App 控制器：到点提醒队列（保持 Qt-free）

`App` 改为「入队 + 逐条呈现」，不再在 `handle_reminder_due` 里直接 `say`：

- 新增 `self._due_queue: list[Reminder] = []` 与 `self._alert_active: bool = False`。
- `handle_reminder_due(reminder)`：`self._due_queue.append(reminder)`；若 `not self._alert_active` 则 `self._present_next_due()`。
- `_present_next_due()`：若队列空，返回；否则 `r = self._due_queue.pop(0)`，`self._alert_active = True`，`self.pet.show_alert(f"⏰ {r.text}")`，`self.notifier.toast("desk-buddy 提醒", r.text)`，`self.notifier.play_sound()`。
- `on_alert_dismissed()`：`self._alert_active = False`；`self._present_next_due()`（关一个弹下一个）。
- `on_alert_nag()`：`self.notifier.play_sound()`（30s 催铃；仅声音）。

`App` 仍只依赖注入的 `pet`（需 `show_alert(text)`，`say`/`set_state` 仍在）与 `notifier`（`toast`/`play_sound`）。无 Qt 依赖，可用 FakePet/FakeNotifier 单测。

> 注：`config.sound_enabled` 仍约束声音——`_present_next_due` 与 `on_alert_nag` 播放前检查 `self.config.sound_enabled`（沿用现有「声音可选」语义）。toast 始终弹。

## 4. main 接线 + 关闭漫游（`main.py`）

- 信号接线新增：`pet.alert_dismissed.connect(controller.on_alert_dismissed)`、`pet.alert_nag.connect(controller.on_alert_nag)`。
- `scheduler` 仍 `Scheduler(store, controller.handle_reminder_due)`；启动 `scheduler.tick(now)` 把错过的全部入队，由用户逐一关闭过完。
- **关闭漫游**：把 `pet.set_roaming(config.roam_enabled)` 改为 `pet.set_roaming(False)`（漫游代码保留）。

## 5. 数据流

- **运行中到点**：`scheduler.tick` → `handle_reminder_due(r)` 入队 →（空闲则）持久弹窗 + toast + 铃 → 用户点「知道了」→ 弹下一条（若有）。未关期间每 30s 响铃。
- **重启补漏**：启动 tick 把所有过期未提醒的逐条入队 → 弹第一条 → 关一条弹一条，直到队列空。`scheduler` 在 tick 时已将它们 `mark_notified`，重启不会重复。

## 6. 测试

App（FakePet 记录 `show_alert` 调用与文字；FakeNotifier 记录 toast/sound；无 Qt）：
- 入队后立即呈现第一条：`handle_reminder_due` 一次 → `show_alert` 被调用 1 次、toast 1 次、sound 1 次、`_alert_active` 为 True。
- 同时只一条：连续 `handle_reminder_due` 三次 → 只 `show_alert` 1 次（其余在队列）。
- 关一个弹下一个：上一步后 `on_alert_dismissed()` → 呈现第二条；再 dismiss → 第三条；再 dismiss → 不再呈现、`_alert_active` False。
- 催铃：`on_alert_nag()` → `notifier` sound +1（且不动队列/弹窗）。
- 声音开关：`sound_enabled=False` 时 `_present_next_due`/`on_alert_nag` 不播声，但 toast 仍弹。

PetWidget（offscreen）：
- `show_alert("x")` 后弹窗可见（`_alert.isHidden() is False`），且**无自动隐藏**（无 `_alert` 的 singleShot 计时；可断言不存在自动隐藏定时器或显示后仍可见）。
- 「知道了」按钮 `.click()` → 弹窗隐藏 + 发 `alert_dismissed`。
- 催铃定时器：`show_alert` 后该定时器 `isActive()` 为 True、间隔 `ALERT_NAG_MS`；手动触发其 timeout → 发 `alert_nag`；dismiss 后定时器停。
- 现有 say/输入条/拖动/点击/漫游接口测试继续通过。

main 的弹窗视觉/真机交互手动验证。

## 7. 文件影响

| 文件 | 改动 |
|------|------|
| `src/desk_buddy/pet_widget.py` | 新增 ReminderAlert 弹窗（卡片+「知道了」）、`show_alert(text)`、信号 `alert_dismissed`/`alert_nag`、30s 催铃定时器、拖动跟随；常量 `ALERT_NAG_MS` |
| `src/desk_buddy/app.py` | 到点提醒队列：`handle_reminder_due` 入队、`_present_next_due`、`on_alert_dismissed`、`on_alert_nag`、`_alert_active`；声音受 `sound_enabled` 约束 |
| `src/desk_buddy/main.py` | 接 `alert_dismissed`/`alert_nag`；`set_roaming(False)` |
| `tests/test_app.py` | 改/加：队列呈现、关闭弹下一条、催铃、声音开关 |
| `tests/test_pet_widget.py` | 加：`show_alert`/不自动关/「知道了」dismiss/催铃定时器 |

其余模块（models/config/store/scheduler/llm/brain/notify）不变。

## 8. 风险/注意

- 现有 `test_app.py` 里断言「到点提醒走 `pet.say` + toast + sound」的用例（`test_reminder_due_bubbles_toasts_and_sounds`、`test_reminder_due_respects_sound_disabled`）语义改变（改走 `show_alert` + 队列），需相应改写。
- 30s 催铃在真机靠 QTimer 事件循环；单测里手动触发 timeout 验证信号即可，不依赖真实计时。
