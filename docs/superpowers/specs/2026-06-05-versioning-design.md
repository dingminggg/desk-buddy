# 版本概念 — 设计

日期：2026-06-05

## 问题

项目没有可用的版本概念：`pyproject.toml` 写死 `0.1.0` 从未更新，代码无
`__version__`，无 git tag，exe 不显示版本。装了某个 exe 无法判断是哪一版、
含哪些修复，只能靠文件时间戳。

## 方案（推荐档：单一可信源 + git tag）

1. **单一可信源 `__version__`**：在 `src/desk_buddy/__init__.py` 定义
   `__version__ = "0.2.0"`。`pyproject.toml` 改为 dynamic version，从该属性读取，
   消除"两处版本号"的隐患。
2. **设置窗口显示版本**：`main.py` 的设置对话框标题改为
   `desk-buddy 设置 v{__version__}`，运行时一眼可见装的是哪版。
3. **git tag**：当前状态打 `v0.2.0`。

### 版本号起点

定为 `0.2.0`（非 0.1.0）：自 0.1.0 之后已加入 CC 权限确认联动、提醒声音、
青蛙动画、CC 会话项目名显示、孤儿 pending 清理等一批功能，0.2.0 更贴近现状。

## 不做（YAGNI）

- 不做构建期注入 git 哈希/构建时间（档 3）。
- 不写 CHANGELOG（档 4）。
- 不做自动发布流水线。
- 需要时再加。

## 测试

- `__version__` 存在且形如 `x.y.z`。
- `pyproject.toml` 用 dynamic version 引用 `desk_buddy.__version__`，
  而非硬编码字面量（防止双版本源回归）。
- 设置对话框标题为 UI 字符串（main.py UI 不在单测覆盖内），实现后人工确认。
