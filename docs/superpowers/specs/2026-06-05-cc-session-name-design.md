# CC 确认卡片显示项目名 — 设计

日期：2026-06-05

## 问题

多开 Claude Code 窗口时，桌宠的 CC 确认卡片只显示固定文案
`🤖 Claude Code 在等你确认`，用户不知道是哪一个会话在等确认。

## 方案

在卡片上显示发起确认的会话所属**项目目录名**（`cwd` 的最后一段）。多开通常对应
不同项目，目录名最好认。

### 取名规则

集中在 `cc_signals` 一处：取 `cwd` 的 basename；拿不到 `cwd`（缺失/空/旧文件）
时回退成 `Claude Code`。

### 数据流改动

1. **`hooks/notify.py`**：从负载多读 `cwd`，传给 `write_pending`。
2. **`cc_signals.py`**
   - `write_pending(session_id, message, cwd="")`：pending JSON 多存 `cwd` 字段。
   - `read_pending()`：返回值由 `set[str]` 改为 **`dict[session_id -> 显示名]`**。
     `bool(dict)` 判空照常可用；显示名在此推导（basename 或回退）。
3. **`main.py`**：轮询把 `read_pending()`（dict）整个传给 `update_cc_pending`。
4. **`app.py`**
   - `update_cc_pending(pending: dict)`：内部记一份当前会话名集合 `_cc_names`。
     "有无变化"判断从「bool 变没变」升级为「**bool 或会话名集合变没变**」，
     使多开时新会话加入能刷新卡片文字。
   - 卡片文案：
     - 单个：`🤖 desk-buddy 在等你确认`
     - 多个：`🤖 2 个会话在等你确认：desk-buddy、browser-harness`（名字去重、排序）
   - 已在显示 CC 卡时集合变了 → 就地 `pet.show_alert` 更新文字，**不重置响铃计数**
     （避免又从头响满 3 次）。

### 不改动

提醒抢占 CC 的仲裁逻辑、响铃上限 `CC_MAX_RINGS`、`clear.py`（只用 session_id）。

## 测试

- `test_cc_signals.py`：新返回结构（dict）、cwd 存读、旧文件无 cwd 回退、basename 推导。
- `test_app.py`：单会话文案、多会话文案（去重排序）、集合变化就地刷新且不重置响铃、
  清空后收起 CC 卡、reminder 抢占行为不回归。

## YAGNI

不做同目录多开的二次区分（短 id / 首条提问）——用户确认多开基本是不同项目。
回退名固定 `Claude Code`，不引入配置项。
