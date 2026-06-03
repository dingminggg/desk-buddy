# desk-buddy LLM 调用异步化（动画不卡）设计

> 日期：2026-06-03
> 状态：设计已确认，待转实现计划
> 关系：在 v1 基础上修复「调 API 时青蛙动画卡住、窗口无响应」

## 1. 背景与目标

现状：用户发消息后，`App.handle_user_text` 同步调用 `brain.parse → provider.chat → requests.post`，这段网络请求**跑在 Qt 主线程**，阻塞期间事件循环停转——QMovie 青蛙动画冻住、窗口无响应（几秒）。

目标：把联网调用挪到后台线程，主线程事件循环不被阻塞，动画照常播放；拿到结果再回主线程更新存储/气泡。

**已确认决策**
- 等待期间冒「让我想想…」气泡（自动消失气泡，复用 `say()`）。
- 处理中再发新消息：忽略并冒「等我把上一句想完～」（同时只一条在飞）。
- 线程方式：可注入的「后台执行器」抽象；默认同步执行器（保持 App 可测），`main` 注入基于 `QThreadPool` 的真实执行器。

非目标（YAGNI）：不做输入排队、不做取消、不做并发多请求；不改提醒/弹窗/漫游逻辑。

## 2. 后台执行器抽象（解耦 Qt，保持 App 可测）

定义执行器接口：`run(fn, on_done, on_error)`——在后台执行 `fn()`，成功则在**主线程**调 `on_done(result)`，抛异常则在主线程调 `on_error(exc)`。

- **SyncRunner**（放 `app.py`，纯 Python，作 App 默认）：当场执行 `fn`，`try/except Exception` 决定调 `on_done`/`on_error`。用于单测与"无 Qt"场景，行为与原同步流程等价。
  ```python
  class SyncRunner:
      def run(self, fn, on_done, on_error):
          try:
              result = fn()
          except Exception as exc:  # noqa: BLE001
              on_error(exc)
          else:
              on_done(result)
  ```
- **QtRunner**（新文件 `src/desk_buddy/qt_runner.py`）：用 `QThreadPool` 跑 `QRunnable`；worker 完成时通过一个建在主线程的 `QObject` 信号（`done`/`error`，参数 `object`）发回结果，Qt 队列投递保证 `on_done`/`on_error` 在主线程执行。需持有信号对象引用直到完成（用一个集合存活、完成后移除），避免被 GC。

## 3. `App` 异步化（`app.py`）

- 构造签名加可选 `runner`：`def __init__(self, config, store, brain, pet, notifier, runner=None)`；`self.runner = runner or SyncRunner()`。新增 `self._busy = False`。
- `handle_user_text(text)`：
  ```python
  if self._busy:
      self.pet.say("等我把上一句想完～")
      return
  self._busy = True
  self.pet.say("让我想想…")
  now = datetime.now()
  self.runner.run(
      lambda: self.brain.parse(text, now),
      lambda intent: self._on_parsed(intent, text),
      lambda exc: self._on_parse_error(exc, text),
  )
  ```
- `_on_parsed(intent, text)`：`self._busy = False`，按 `intent.action` 派发——把现有 add/query/complete/cancel/clarify 分支逻辑（含 `_do_add(intent, text)` 等调用）原样移入。
- `_on_parse_error(exc, text)`：`self._busy = False`；若 `isinstance(exc, LLMError)`：`self.store.save_draft(text)` + `self.pet.say("我现在连不上脑子，先把你的话记下了，稍等再说～")`；否则 `self.pet.say("出了点小问题，稍后再说～")`。
- **只有 `brain.parse`（联网）在后台**；`_on_parsed`/`_on_parse_error` 在主线程回调里跑，存储（sqlite）与气泡均主线程操作，不跨线程。
- 到点提醒队列（`handle_reminder_due`/`_present_next_due`/`on_alert_dismissed`/`on_alert_nag`）与 `_busy` 无关，照常工作。

## 4. main 接线（`main.py`）

```python
from .qt_runner import QtRunner
...
controller = App(config, store, brain, pet, notify, runner=QtRunner())
```
其余不变。

## 5. 数据流

发消息 → `handle_user_text`（主线程）→ 冒「让我想想…」+ 后台线程跑 `brain.parse`（其间事件循环继续、青蛙照动）→ 完成后 Qt 信号把结果投回主线程 → `_on_parsed` 派发（存储/气泡）或 `_on_parse_error`（草稿/道歉）。处理中再发 → 「等我把上一句想完～」忽略。

## 6. 测试

- **现有 App 测试**：用默认 `SyncRunner`，流程等价；`pet.said` 里会多一条开头的「让我想想…」。断言为"truthy"或 `[-1]` 的用例仍成立；如有断言具体首条/数量的，相应微调。
- **新增**（用可控 `FakeRunner`：保存 `fn`/`on_done`/`on_error`，由测试手动触发完成）：
  - 首条气泡为「让我想想…」。
  - 处理中再发：第二次 `handle_user_text` 只冒「等我把上一句想完～」，且 runner 只收到一个任务；触发第一个完成后能正常派发，且 `_busy` 复位。
  - 成功路径：手动 `on_done(intent)` → 按 action 派发（如 ADD 入库）。
  - 错误路径：手动 `on_error(LLMError(...))` → 存草稿 + 道歉；`on_error(其它异常)` → 通用提示、不存草稿。
- **QtRunner**（offscreen 轻测）：`run` 一个返回固定值的 `fn`，用 `QCoreApplication.processEvents()` 轮询（带超时上限，如 ~2s）直到 `on_done` 收到该值；再测一个抛异常的 fn 走 `on_error`。

## 7. 文件影响

| 文件 | 改动 |
|------|------|
| `src/desk_buddy/app.py` | 加 `SyncRunner`；`__init__` 增 `runner`/`_busy`；`handle_user_text` 改异步 + busy 守卫 + 思考气泡；新增 `_on_parsed`/`_on_parse_error`（派发逻辑迁入） |
| `src/desk_buddy/qt_runner.py` | 新增 `QtRunner`（QThreadPool + 主线程信号回调） |
| `src/desk_buddy/main.py` | 给 App 注入 `QtRunner()` |
| `tests/test_app.py` | 适配默认 SyncRunner（思考气泡）；加 FakeRunner 的 busy/思考/成功/错误测试 |
| `tests/test_qt_runner.py` | 新增 QtRunner offscreen 轻测 |

其余模块（models/config/store/scheduler/llm/brain/notify/pet_widget）不变。

## 8. 风险/注意

- 「让我想想…」用自动消失气泡（6s）；若 API >6s 它先消失，青蛙仍在动、结果回来再冒新气泡——可接受。
- 后台线程只碰 `brain.parse`（联网，无共享可变状态）；不在后台线程访问 sqlite/UI，避免线程安全问题。
- QtRunner 必须持有信号对象引用至完成，否则结果可能因 GC 丢失（实现中用存活集合管理）。
