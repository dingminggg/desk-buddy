# desk-buddy 延迟配置设计（宠物先行 + 点击/右键触发设置）

> 日期：2026-06-03
> 状态：设计已确认，待转实现计划
> 关系：在已交付的 [desk-buddy v1](2026-06-03-desk-buddy-design.md) 基础上的增量改动

## 1. 背景与目标

v1 现状：启动时若未配置，**先弹阻塞式设置框，填完才出现宠物**；且设置框把 `https://api.openai.com/v1`、`gpt-4o-mini` **预填**进输入框——用户直接点保存这些字面量就被当成真实配置存盘，等于「代码里写死配置」。

目标改为：

1. **宠物先跑起来**，再引导填配置——不阻塞启动。
2. **未配置时点宠物 → 弹设置框**；填完保存即可用。
3. **已配置后也能改**：右键宠物 → 菜单「设置」唤出同一设置框。
4. **代码里不再有会被存盘的硬编码配置值**（占位提示不算）。

非目标（YAGNI）：右键菜单 v1 仅「设置」一项；不做配置连通性预校验（保存后下次发消息自然知道通不通）；不做漫游开关等其它菜单项（结构预留，本期不加）。

## 2. 启动流程改动（`main.py`）

去掉启动前的阻塞配置框。无论是否已配置，都照常构建 `store / brain / pet / controller` 并让宠物先出现：

```
启动 → QApplication
     → load_config(config.json)
     → 建 store、brain=Brain(build_provider(config))、pet、controller=App(...)
       （未配置时 build_provider 仍能构造空适配器，不报错）
     → 接线信号（见 §3）
     → scheduler.tick(now) 启动补漏 + QTimer(TICK_INTERVAL_MS)
     → pet.show()
     → 气泡：未配置「我还没连上大脑，点我设置一下吧～」
             已配置「我在啦～ 点我说要提醒啥～」
```

未配置时 `build_provider(config)` 返回 `OpenAICompatibleProvider("", "", "")`，构造不报错；因为未配置时点击只开设置框（不开输入条，见 §3），用户无法在配置前发消息，规避「没大脑就发消息」的问题。

## 3. 统一的「打开设置」处理器与信号接线（`main.py`）

新增一个处理器，未配置点击与右键设置**复用**它：

```python
def open_settings():
    # _run_setup_dialog 仅在「保存」被确认时写回（见 §5）
    changed = _run_setup_dialog(config)          # 就地修改 config，返回是否已保存
    if changed:
        save_config(config, config_path)
        if config.is_configured:
            controller.brain = Brain(build_provider(config))   # 重建大脑
            pet.say("大脑接上啦～现在可以跟我说要提醒啥啦！")

def on_pet_clicked():
    if config.is_configured:
        pet.prompt_input()        # 已配置：开输入条（行为同 v1 的点击）
    else:
        open_settings()           # 未配置：开设置框
```

接线：

| 信号 | 连接目标 |
|------|----------|
| `pet.clicked`（左键非拖拽点击） | `on_pet_clicked` |
| `pet.settings_requested`（右键菜单选「设置」） | `open_settings` |
| `pet.user_said`（输入条回车） | `controller.handle_user_text`（不变） |

`controller.brain` 为 `App` 已有的公开属性，main 直接重赋值即可重建大脑；`App` 本身保持 Qt-free、不需改动（现有 9 个 App 测试不受影响）。

## 4. PetWidget 改动（`pet_widget.py`）

把「点击后做什么」的决定权从控件移到控制器：

- 新增信号 `clicked = Signal()`：左键**非拖拽**点击释放时发出（原本直接调用的 `_show_input()` 不再在释放时调用）。
- `_show_input()` 改名为公开方法 `prompt_input()`（行为不变：在宠物正下方显示输入条并聚焦）。
- 新增信号 `settings_requested = Signal()` 与公开方法 `request_settings()`（仅 `self.settings_requested.emit()`）。
- 右键点击：弹 `QMenu`，含一项「设置」，其 `triggered` 连到 `self.request_settings`。菜单结构预留，本期只此一项。

鼠标释放判定（沿用 v1 的拖拽/点击区分）：是点击则 `self.clicked.emit()`，是拖拽则不发。

## 5. 设置框改动（`_run_setup_dialog`）

签名仍为 `_run_setup_dialog(config: Config) -> bool`（返回是否已保存确认），改动：

- **占位提示替代预填默认值**（避免硬编码配置被存盘）：
  ```python
  base = QLineEdit(config.base_url);  base.setPlaceholderText("https://api.openai.com/v1")
  model = QLineEdit(config.model);    model.setPlaceholderText("gpt-4o-mini")
  key = QLineEdit(config.api_key);    key.setEchoMode(QLineEdit.Password)
  ```
  - 未配置时 `config.base_url` 为空串 → 字段为空、只显示灰色占位提示，不输入就不保存。
  - 已配置时用现值回填，便于修改。
- **仅在「保存」确认时写回**：`if dialog.exec() == QDialog.DialogCode.Accepted:` 才把字段写回 `config` 并返回 `True`；点窗口 X 关闭＝拒绝，返回 `False`，**不改动现有配置**。这对「改配置中途取消」至关重要。

## 6. 数据流

- **首次启动未配置**：宠物出现 + 提示气泡 → 用户左键点宠物 → 设置框 → 填 base_url/model/api_key → 保存 → 写 config.json + 重建 brain → 气泡「大脑接上啦」→ 之后左键点宠物开输入条正常提醒。
- **已配置换源/换模型**：右键宠物 → 菜单「设置」→ 设置框（回填现值）→ 改 → 保存 → 写 config.json + 重建 brain。中途点 X → 不变。
- **配置文件**：始终只存在 `config.json`（API key 不入库），reminders.db 只存提醒/草稿，沿用 v1。

## 7. 测试

- `PetWidget`（offscreen 冒烟，新增）：
  1. 左键非拖拽点击释放 → 发出 `clicked`。
  2. `prompt_input()` → 输入条可见。
  3. `request_settings()` → 发出 `settings_requested`。
- 现有 49 个测试逻辑不受影响，继续全绿。
- `main` 的设置框 / 右键菜单 `exec()` 含 Qt 模态弹窗，**手动验证**（沿用 v1「鼠标/绘制/模态不写死自动化测试」的约定）。手动验证脚本见实现计划。

## 8. 影响面小结

| 文件 | 改动 |
|------|------|
| `src/desk_buddy/pet_widget.py` | 加 `clicked`/`settings_requested` 信号、`prompt_input()`/`request_settings()`、右键菜单；左键释放改发信号 |
| `src/desk_buddy/main.py` | 去掉阻塞配置框；加 `open_settings`/`on_pet_clicked` 并接线；`_run_setup_dialog` 改占位提示 + 仅保存时写回（返回 bool） |
| `tests/test_pet_widget.py` | 新增 3 个 offscreen 测试 |
| `src/desk_buddy/app.py` | 不改（`brain` 为公开属性，main 重赋值） |

其余模块（models/config/store/scheduler/llm/brain/notify）不变。
