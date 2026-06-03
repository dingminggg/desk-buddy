# desk-buddy 设计文档

> 日期：2026-06-03
> 状态：设计已确认，待转实现计划

## 1. 整体定位

一只 **Windows 桌面悬浮宠物**（Python + PySide6），核心是**自然语言提醒工具**。用户用大白话跟它说话，程序在运行时调用 LLM 把话解析成结构化提醒，本地存储，到点时角色冒气泡 + 系统通知提醒用户。角色浮在桌面上，可手动拖动，也可自主漫游（可开关）。

v1 定位为**专注提醒器**：对话只用于定/查/完成/取消提醒 + 偶尔问候，不做完整闲聊与主动唠叨。

## 2. 关键决策（已确认）

| 项 | 决策 |
|----|------|
| 交互布局 | A · 极简悬浮（角色头顶气泡说话，点击正下方弹小输入条） |
| 技术栈 | Python 3.11+ + PySide6 |
| 运行时智能 | 接入 LLM API 做"自然语言 → 结构化提醒"解析 |
| LLM 后端 | **可插拔**，主打 OpenAI 兼容端点，方便随时换免费模型 |
| v1 范围 | 专注提醒器 |
| 移动方式 | 手动拖动 + 自主漫游（漫游可开关） |
| 存储 | SQLite |
| 删除 | 一律软删除（状态标记），绝不真删 |

## 3. 模块拆分

每个模块职责单一、通过明确接口通信、可独立测试。

| 模块 | 职责 | 依赖 | 不负责 |
|------|------|------|--------|
| **PetWidget** | 透明无边框置顶窗口；绘制角色/动画帧、拖动、自主漫游、冒气泡、点击弹输入条。对外暴露 `say(text)`、`set_state(idle/walking/...)`，发出信号 `user_said(text)`。 | PySide6 | 解析、存储、联网 |
| **ReminderStore** | 提醒的本地增删改查。删 = 软删除（状态标记）。返回纯数据对象。 | SQLite | UI、联网 |
| **Scheduler** | 定时器（每 ~20s tick），检查到点提醒，发出信号 `reminder_due(reminder)`；处理简单重复逻辑。 | ReminderStore | UI、联网、解析 |
| **Brain** | 唯一联网模块。把"用户文本 + 当前时间"交给 LLMProvider，返回结构化意图。负责解析结果校验与重试。 | LLMProvider | UI、存储 |
| **LLMProvider**（接口） | 抽象 LLM 后端，单一方法 `chat(system, user) -> text`。 | — | 业务逻辑 |
| **App 控制器** | 接线各模块：输入→Brain→Store→气泡反馈；到点→气泡+通知+声音。 | 全部 | — |
| **Config** | API key、`provider/base_url/model/api_key`、设置（漫游开关、声音、角色）。本地存，key 不入库。 | — | — |

## 4. 可插拔 LLM 后端（重点）

**面向接口，不绑死任何厂商。** 用户后续可自由切换免费模型源。

```
Brain
 └── LLMProvider（抽象接口）  ← 只定义 chat(system, user) -> text
      ├── OpenAICompatibleProvider   ← 主力
      └── AnthropicProvider（可选）
```

**为什么主打 OpenAI 兼容适配器：** 绝大多数免费/廉价模型接口都暴露 OpenAI 兼容的 `/chat/completions` 端点（OpenRouter、Groq、DeepSeek、Moonshot、本地 Ollama / LM Studio 等）。写一个适配器即可覆盖，换源只改配置：

```
provider  = openai_compatible
base_url  = https://xxx/v1   # 换接口只改这里
model     = xxx              # 换模型只改这里
api_key   = sk-xxx
```

**结构化解析做成模型无关**（不依赖厂商专属 tool-use，因为弱模型不一定支持）：

1. system prompt 要求模型严格按 JSON 返回 `{action, time, text}`；
2. 本地用 pydantic 解析 + 校验；
3. 格式不对则带错误反馈重试一次；
4. 仍失败才降级反问用户。

**对其他模块零影响**：ReminderStore / Scheduler / PetWidget 只跟"结构化提醒对象"打交道，换后端是 Brain 内部的事。

## 5. 数据流

- **定提醒**：点角色 → 输入"明天下午3点提醒我开会" → PetWidget 发 `user_said` → Brain 带当前时间问 LLM → 返回 `{add, 2026-06-04 15:00, "开会"}` → 控制器存入 ReminderStore → PetWidget.say("好的，明天3点开会记下啦！")
- **到点**：Scheduler 发现到点 → 控制器 → 角色走到角落 + 气泡 + Windows toast + 可选提示音 → 用户可标记完成。
- **查/取消**："我今天还有啥提醒" / "取消开会那个" → Brain 解析 → ReminderStore 查询 / 软删除 → 气泡回结果。

## 6. 提醒数据模型

```
Reminder {
  id          整数主键
  text        事项文本
  due_at      到点时间（datetime）
  status      待办 / 已完成 / 已取消
  repeat      无 / 每天（v1 仅简单重复）
  created_at  创建时间
}
```

## 7. 容错（治本，不只兜底）

- **连不上 API**：气泡提示"我现在连不上脑子，稍等"，并把原话存成草稿，不丢内容。
- **时间说不清**：LLM 返回"需要追问" → 气泡反问"今天还是明天？"。
- **没填 API key**：首次启动引导填写。
- **删除**：一律软删除（status=已取消），绝不真删。

## 8. 成本控制

- 仅在用户真正发消息时调 API（发呆不调）。
- 可直接挂免费模型源，接近零成本。
- 若后端为支持缓存的厂商，system prompt 走 prompt caching 降费。

## 9. 关闭后的提醒

v1 提醒**仅在程序运行时**触发。启动时加载未完成提醒；若有"程序关着时已过期"的，启动时补提醒（漏接）。开机自启留到以后。

## 10. v1 范围（YAGNI）

**做：**
- 悬浮可拖角色、自主漫游（可关）
- 点击弹输入条
- 自然语言 增 / 查 / 完成 / 取消提醒
- 本地 SQLite 存储
- 到点通知（气泡 + Windows toast + 可选声音）
- 启动补漏
- 首次填 API key 引导
- 可插拔 LLM 后端（OpenAI 兼容适配器）

**暂不做：**
- 完整闲聊 / 主动唠叨
- 复杂重复规则
- 换肤 / 角色定制
- 云同步
- 开机自启
- 移动端

## 11. 技术细节

- Python 3.11+、PySide6、pydantic（结构化校验）
- SQLite（标准库）
- Windows toast 通知（如 plyer / win10toast）
- 角色 v1 用占位形象，真实美术后续补
- 打包：PyInstaller 出 exe

## 12. 默认取值

| 项 | 默认 |
|----|------|
| 存储 | SQLite |
| 通知 | 气泡 + Windows toast + 可选声音 |
| 角色 | v1 占位形象 |
| 触发 | 仅运行时 + 启动补漏 |
