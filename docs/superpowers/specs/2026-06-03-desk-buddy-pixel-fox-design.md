# desk-buddy 像素小狐狸形象设计

> 日期：2026-06-03
> 状态：设计已确认，待转实现计划
> 关系：替换 [desk-buddy v1](2026-06-03-desk-buddy-design.md) 里的占位圆形形象

## 1. 背景与目标

当前 `PetWidget.paintEvent` 只画一个椭圆，`set_state(idle/walking)` 仅切换填充颜色（`_STATE_COLORS`）。目标：换成**代码手绘的像素风小狐狸**，带每状态 2 帧轻动画，不引入外部图片素材。

**决策（已确认）**
- 素材来源：**代码手绘像素矩阵**（字符网格 → 调色板 → QPainter 放大像素），无外部 PNG、无版权问题、可进版本控制。
- 形象：**小狐狸**（橙白配色，尖耳大尾）。
- 动画：**每状态 2 帧轻动画**——idle 轻微上下浮 + 偶尔眨眼；walking 两帧踏步/尾巴交替。

非目标（YAGNI）：不做左右朝向翻转；不超过 idle/walking 两个状态；不做 PNG 外部素材加载；不做超过 2 帧的复杂动画。

## 2. 模块拆分：新增 `sprite.py`

把形象数据与渲染从 `PetWidget` 独立出来，职责单一、可独立单测。

- **调色板** `PALETTE: dict[str, QColor]`：字符 → 颜色。`.` 表示透明（不绘制）。狐狸用色约为：`o` 橙 `#e8772e`、`l` 浅橙/腹 `#f6b26b`、`w` 白 `#ffffff`、`k` 深褐描边/眼 `#3a2a1a`、`p` 鼻/粉 `#d9534f`（具体色值在实现期可微调）。
- **帧数据**：每帧是 `list[str]`，每个字符串一行，所有行**等长**（统一网格宽），字符都在 `PALETTE` 内或为 `.`。网格尺寸固定 **16×16**。
- **帧集合** `FRAMES: dict[str, list[list[str]]]`，键为状态名，值为该状态的 2 帧：
  ```python
  FRAMES = {
      "idle":    [IDLE_0, IDLE_1],
      "walking": [WALK_0, WALK_1],
  }
  ```
- **渲染函数** `build_pixmap(rows: list[str], scale: int) -> QPixmap`：
  - 创建 `QPixmap(cols*scale, len(rows)*scale)`，`fill(Qt.transparent)`。
  - 用 `QPainter` 逐格填 `scale×scale` 色块；`.` 跳过（保持透明）。
  - 返回的 pixmap 即「原生网格 × scale」尺寸。
  - 关闭抗锯齿/平滑（纯色块本就锐利）。

`sprite.py` 仅依赖 PySide6 的 `QColor/QPixmap/QPainter/Qt`，不依赖 `PetWidget`。

## 3. PetWidget 改造

- 删除 `_STATE_COLORS` 与 `paintEvent` 里画椭圆的代码。
- `__init__`：
  - 预渲染所有帧为 QPixmap 并缓存：`self._frames = {state: [build_pixmap(f, SPRITE_SCALE) for f in frames] for state, frames in FRAMES.items()}`，其中 `SPRITE_SCALE` 使 `16*SPRITE_SCALE == PET_SIZE`（PET_SIZE=96 → SPRITE_SCALE=6）。
  - `self._frame_index = 0`。
  - 新增动画定时器 `self._anim_timer`（`ANIM_INTERVAL_MS`，约 400ms），`timeout` → `_advance_frame`。
- `paintEvent`：取 `self._frames[self._state][self._frame_index]`，用 `painter.drawPixmap(0, 0, pixmap)`；绘制前 `painter.setRenderHint(QPainter.SmoothPixmapTransform, False)` 保锐（pixmap 已是目标尺寸，理论上无需缩放，但显式关平滑稳妥）。当 `self._state` 不在 `_frames` 中时回退到 `"idle"`。
- `_advance_frame`：`self._frame_index = (self._frame_index + 1) % 2`，`self.update()`。
- `set_state(state)`（**对外接口不变**）：设 `self._state`，并将 `self._frame_index` 归 0，`self.update()`。
- 动画定时器生命周期：在 `__init__` 末尾 `self._anim_timer.start(ANIM_INTERVAL_MS)`（窗口未显示时定时器开销可忽略；保持简单，不随显隐启停）。

`PET_SIZE` 仍为 96。`set_state` / `say` / 拖动 / 漫游 / 输入条等其余行为不变。

## 4. 形象与动画细节（实现期迭代）

- 先把小狐狸 16×16 矩阵画出来，**用 offscreen Qt 渲染成 PNG 贴给用户确认**；用户反馈（如「耳朵大点」「颜色深点」）→ 改矩阵 → 再渲染，直到满意。这一像素微调属实现细节。
- idle 两帧：身体/头整体上下浮 1px；其中一帧把眼睛行改成闭眼（眨眼）。
- walking 两帧：腿与尾巴位置交替，制造踏步感。
- 两帧之间网格尺寸保持一致（都 16×16），仅像素内容不同。

## 5. 测试

`tests/test_sprite.py`（headless，offscreen Qt）：
- `FRAMES` 含 `"idle"` 与 `"walking"`，各恰好 2 帧；每帧所有行等长、行数=16、列数=16。
- 每帧用到的字符都在 `PALETTE` 或为 `.`。
- `build_pixmap(rows, scale)` 返回 `QPixmap`，尺寸 = `(16*scale, 16*scale)`，且非空（`isNull()` 为 False）。
- 透明像素：某个已知 `.` 格在渲染图中 alpha=0；某个已知 body 格颜色等于对应 `PALETTE` 色（用 `pixmap.toImage().pixelColor(x, y)` 取中心点校验）。

`tests/test_pet_widget.py`（沿用并微调）：
- 现有 offscreen 测试（say/状态/漫游/点击/拖动/输入条）继续通过。
- `set_state("walking")` 后再 `set_state("idle")` 不崩；`_advance_frame()` 调用后 `_frame_index` 在 {0,1} 内循环且不崩（直接调内部方法，不依赖定时器真触发）。
- 形象的像素外观本身不写死自动化断言（视觉由渲染预览人工确认，沿用「绘制/视觉手动验证」约定）。

## 6. 文件影响

| 文件 | 改动 |
|------|------|
| `src/desk_buddy/sprite.py` | 新增：`PALETTE`、`FRAMES`（idle/walking 各 2 帧）、`build_pixmap` |
| `src/desk_buddy/pet_widget.py` | 用 sprite 帧 + 动画定时器替换 `_STATE_COLORS`/椭圆；新增 `_anim_timer`/`_frame_index`/`_advance_frame`；`paintEvent`/`set_state` 改造 |
| `tests/test_sprite.py` | 新增（见 §5） |
| `tests/test_pet_widget.py` | 微调状态/帧推进测试 |

其余模块（models/config/store/scheduler/llm/brain/notify/app/main）不变。
