# desk-buddy 青蛙 GIF 形象设计

> 日期：2026-06-03
> 状态：设计已确认，待转实现计划
> 关系：替换 [像素小狐狸](2026-06-03-desk-buddy-pixel-fox-design.md)，改用动图 GIF 作宠物本体

## 1. 背景与目标

当前宠物本体是代码绘制的像素小狐狸（`sprite.py` + `PetWidget.paintEvent` 画缓存帧 + 动画定时器）。用户提供了一张动图 `frog.gif`（卡通小青蛙），要把它作为**宠物本体**。

GIF 实测：320×320、33 帧、带透明通道、四角 alpha=0（本就画在透明背景上）。

**决策（已确认）**
- 渲染：用 `QMovie` 播放 GIF，缩放到 **128px**（卡通图，开平滑缩放）。
- 显示尺寸：`PET_SIZE` 由 96 → **128**。
- 状态：只有一段动画，idle/walking 用同一动画；`set_state` 接口保留但不改变外观。
- 缺失处理：**只用青蛙**——删除像素狐狸代码；GIF 缺失/加载失败时空白显示且不崩溃（不回退狐狸）。
- 资源位置：GIF 移入包内 `src/desk_buddy/assets/frog.gif`，运行时按包路径解析；PyInstaller 打包进 exe。

非目标（YAGNI）：不做多套 GIF/按状态切不同动画、不做左右朝向翻转、不做缺失回退到其它形象、不做边缘描边处理（除非渲染确认有明显白边）。

## 2. 渲染改造（`pet_widget.py`）

- 顶部：移除 `from .sprite import ...`；新增 `from PySide6.QtGui import QMovie`（保留既有 `QPainter`、`QColor`——`QColor` 仍用于输入条阴影）；用 `from pathlib import Path` 解析资源。
- 常量：`PET_SIZE = 128`；删除 `SPRITE_SCALE`、`ANIM_INTERVAL_MS`。资源路径 `_GIF_PATH = Path(__file__).parent / "assets" / "frog.gif"`。
- `__init__`：
  - 删除 sprite 帧缓存（`self._frames`）、`self._frame_index`、动画定时器（`self._anim_timer`）。
  - 新增：
    ```python
    self._movie = QMovie(str(_GIF_PATH))
    self._movie.setScaledSize(QSize(PET_SIZE, PET_SIZE))
    self._movie.frameChanged.connect(self.update)
    if self._movie.isValid():
        self._movie.start()
    ```
  - 需要 `from PySide6.QtCore import QSize`（与现有 `Qt, QTimer, Signal` 同行追加）。
- `paintEvent`：
  ```python
  def paintEvent(self, event):  # noqa: N802
      if not self._movie.isValid():
          return
      painter = QPainter(self)
      painter.drawPixmap(0, 0, self._movie.currentPixmap())
  ```
  （`currentPixmap()` 已是 128×128 缩放后的当前帧，含透明；卡通图缩放用 QMovie 默认平滑，不需关平滑。）
- `set_state(state)`：保留对外签名，仅 `self._state = state`（不再重置帧/改外观）。
- 删除 `_advance_frame`。

其余（拖动 `_moved`/阈值、右键 `设置/退出` 菜单、输入条显隐与跟随、漫游暂停、气泡定位）均不变，且全部引用 `PET_SIZE` 符号，128 自动生效。

## 3. 删除像素狐狸

- 删除 `src/desk_buddy/sprite.py` 与 `tests/test_sprite.py`。
- 确认 `pet_widget.py` 无任何 `sprite` / `build_pixmap` / `FRAMES` / `_STATE_COLORS` 残留引用。

## 4. 资源与打包

- 将 GIF 从项目根 `assets/frog.gif` 移动到包内 `src/desk_buddy/assets/frog.gif`（`git add` 跟踪，约 300KB）。
- `desk_buddy.spec`：`datas` 增加 `("src/desk_buddy/assets/frog.gif", "desk_buddy/assets")`，确保打包进 exe。QMovie 解 GIF 用 Qt 内置 gif 插件，PyInstaller 默认收集 imageformats，一般无需额外配置。
- `README.md`：用法处提到「桌面宠物为青蛙动图」。

## 5. 测试（`tests/test_pet_widget.py`，offscreen）

- 删除依赖 sprite 帧的测试（`test_set_state_resets_frame_and_advance_cycles`、`test_unknown_state_falls_back_to_idle_without_crash`）。
- 新增：
  - `test_pet_size_is_128`：`PET_SIZE == 128`，构造后 `pet.size()` 为 128×128。
  - `test_movie_loaded`：`pet._movie.isValid()` 为 True，`pet._movie.frameCount() > 0`。
  - `test_paint_does_not_crash`：`pet.show(); pet.repaint()` 不抛异常。
  - `set_state("walking")` 后 `set_state("idle")` 不崩（保留一个轻量状态测试）。
- 现有拖动/点击/输入条跟随/漫游/设置信号等测试继续通过；`test_input_bar_follows_pet_on_drag` 用 `PET_SIZE` 符号断言，自动适配 128。
- 真身视觉由 offscreen 渲染 `pet.grab()` 出 PNG 人工确认 + 用户本机运行确认。

## 6. 风险

GIF 为 1-bit（开/关）透明，缩放后边缘**可能有锯齿或白边**。该青蛙四角已透明、是干净卡通，预计可接受；渲染确认若明显，再考虑描边/换 WebP/APNG（本期不做）。

## 7. 文件影响

| 文件 | 改动 |
|------|------|
| `src/desk_buddy/pet_widget.py` | 改：QMovie 替换 sprite 帧渲染；`PET_SIZE=128`；删动画定时器/帧机制；`paintEvent`/`set_state` 改造 |
| `src/desk_buddy/sprite.py` | 删除 |
| `tests/test_sprite.py` | 删除 |
| `tests/test_pet_widget.py` | 删旧帧测试、加 movie/尺寸/绘制测试 |
| `src/desk_buddy/assets/frog.gif` | 新增（从项目根 assets/ 移入包内） |
| `desk_buddy.spec` | datas 增加 gif |
| `README.md` | 提及青蛙形象 |

其余模块（models/config/store/scheduler/llm/brain/notify/app/main）不变。
