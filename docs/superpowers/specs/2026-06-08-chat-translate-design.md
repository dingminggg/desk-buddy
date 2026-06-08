# 桌宠翻译 + 简单问答 — 设计

日期：2026-06-08

## 目标

让桌宠在"这不是提醒操作"时直接回答用户：翻译、简单问答。自动识别（无需前缀），
单轮独立（不记上下文）。

## 方案

复用现有 Intent 管道，新增一个 `chat` 动作；**一次 LLM 调用同时分类并给出答案**，
不加额外往返。翻译就是一种 chat（"翻译成英文：…"），不单独建动作。

### 数据流

1. **`models.py`**：`IntentAction` 增加 `CHAT = "chat"`。
2. **`brain.py`**：扩展 SYSTEM_TEMPLATE——若输入不是 add/query/complete/cancel，
   返回 `{"action":"chat","text":"<直接的答案/译文，简洁>"}`。其余规则不变；
   解析失败仍回退 CLARIFY。
3. **`app.py`**：`_on_parsed` 处理 `IntentAction.CHAT` → `pet.show_answer(intent.text)`。

### 显示：独立"答案卡"

用户选择"手动关闭"。为不污染提醒/CC 的告警卡仲裁状态机（`_alert_kind` 等，
CLAUDE.md 标注为微妙易错），**新增一张独立的答案卡**，与告警卡互不干涉：

- `PetWidget.show_answer(text)`：显示持久卡片，自动换行、设最大宽度（复用
  `ALERT_TEXT_MAX_W` 的折行策略），**不自动消失、不响铃**。
- `PetWidget.hide_answer()`：隐藏。
- 关闭方式：点击答案卡即关（局部隐藏，无需回传 App——App 不持有任何 chat 状态）。
- 新问题到来时 `show_answer` 直接覆盖旧文本。
- 位置与告警卡错开（答案卡在宠物上方，告警卡在下方），避免同时出现时重叠。

App 对 chat 是无状态的：收到 CHAT 只调用 `pet.show_answer`。提醒/CC 流程完全不变。

### 错误处理

`LLMError`（连不上）沿用现有 `_on_parse_error`：存草稿 + 气泡提示离线。瑕疵：
解析失败时分不清原本是提醒还是提问，提问会被存成一条无用草稿——无害，不特殊处理。

## 测试

- **`brain`**：mock provider 返回 chat JSON → `Intent(action=CHAT, text=...)`；
  翻译输入同样走 chat（一条用例）。
- **`app`**：CHAT 意图 → `pet.show_answer(答案)` 被调用且文本正确；
  add/query/complete/cancel **不回归**（沿用现有 fake pet，新增 `show_answer` 记录）。
- **`pet_alert`/`pet_widget`**：`show_answer`/`hide_answer` 显示与隐藏；
  答案卡与告警卡互不影响（显示答案卡不改变 `_alert_kind`）。

## 不做（YAGNI）

多轮上下文记忆、显式前缀（"翻译："）、流式输出、问答历史保存、答案卡响铃。

## 版本

完成后 bump 到 0.3.0（新增能力，minor）。
